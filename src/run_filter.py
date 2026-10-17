"""Transactional local runs; CLI prints counts only, never content."""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import time
import uuid

from .filter_rules import classify_order, extract_orders, merge_orders
from .report import render_report, LABELS
from .wechat_source import ROOT, read_messages, load_upstream, detect_account, IncompleteReadError
from .user_settings import load_user_settings, apply_user_settings, preference_snapshot

RETENTION = 7 * 86400


class RunBusyError(RuntimeError):
    pass


def safe_directory(path):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        if item.exists():
            details = item.lstat()
            if item.is_symlink() or getattr(details, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 1024):
                raise RuntimeError('PRIVATE_PATH_IS_LINK')
    path.mkdir(parents=True, exist_ok=True)
    return path


@contextlib.contextmanager
def run_lock(root):
    root = safe_directory(root)
    lock_path = root / 'run.lock'
    if lock_path.is_symlink():
        raise RuntimeError('LOCK_PATH_IS_LINK')
    with lock_path.open('a+b') as handle:
        handle.seek(0, 2)
        if not handle.tell():
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RunBusyError('RUN_ALREADY_ACTIVE') from None
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def account_root(root, account):
    return safe_directory(Path(root) / 'accounts' / hashlib.sha256(account.encode()).hexdigest())


def read_current(root, account):
    folder = account_root(root, account)
    return read_folder(folder)


def read_folder(folder):
    pointer = folder / 'current.json'
    if not pointer.exists():
        return None
    name = json.loads(pointer.read_text(encoding='utf-8'))['run']
    if not re.fullmatch(r'run-\d+-[a-f0-9]{32}', name):
        raise RuntimeError('INVALID_STATE_POINTER')
    snapshot = folder / name
    if not snapshot.is_dir() or snapshot.is_symlink() or getattr(snapshot.lstat(), 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 1024) or not same_parent(snapshot, folder):
        raise RuntimeError('INVALID_STATE_PATH')
    return {'state': json.loads((snapshot / 'state.json').read_text(encoding='utf-8')),
            'orders': json.loads((snapshot / 'orders.json').read_text(encoding='utf-8')),
            'report': str(snapshot / 'report.html'), 'run': name}


def same_parent(path, parent):
    try:
        # Store application virtualization can produce different lexical paths
        # for the same physical private directory; verify its filesystem identity.
        return Path(path).resolve().parent.samefile(parent)
    except OSError:
        return False


def remove_owned_directory(path, parent, pattern):
    path, parent = Path(path), Path(parent)
    if not re.fullmatch(pattern, path.name) or not same_parent(path, parent):
        raise RuntimeError('CLEANUP_BOUNDARY_VIOLATION')
    for current, dirs, files in os.walk(path, followlinks=False):
        for node in [Path(current), *(Path(current) / name for name in dirs + files)]:
            details = node.lstat()
            if node.is_symlink() or getattr(details, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 1024):
                raise RuntimeError('CLEANUP_LINK_REFUSED')
    shutil.rmtree(path)


def clean_snapshots(folder, current_name, cutoff):
    for child in folder.iterdir():
        match = re.fullmatch(r'run-(\d+)-[a-f0-9]{32}', child.name)
        if not match or child.name == current_name:
            continue
        safe_directory(child)
        try:
            orders = json.loads((child / 'orders.json').read_text(encoding='utf-8'))
            expired_raw = any(s['timestamp'] < cutoff for o in orders for s in o['sources'])
        except (OSError, ValueError, KeyError):
            expired_raw = True  # Incomplete orphan snapshots are not a committed result.
        if int(match.group(1)) < cutoff or expired_raw:
            remove_owned_directory(child, folder, r'run-\d+-[a-f0-9]{32}')


def publish_snapshot(folder, now, state, orders, metadata):
    name = f'run-{now}-{uuid.uuid4().hex}'
    snapshot = safe_directory(folder / name)
    for filename, value in [('state.json', state), ('orders.json', orders)]:
        with (snapshot / filename).open('w', encoding='utf-8') as handle:
            json.dump(value, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
    with (snapshot / 'report.html').open('w', encoding='utf-8') as handle:
        handle.write(render_report(orders, metadata))
        handle.flush()
        os.fsync(handle.fileno())
    pointer_temp = folder / ('current-' + uuid.uuid4().hex + '.tmp')
    with pointer_temp.open('w', encoding='utf-8') as handle:
        json.dump({'run': name}, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(pointer_temp, folder / 'current.json')
    return name, str(snapshot / 'report.html')


def clean_all_accounts(root, now):
    accounts = Path(root) / 'accounts'
    cutoff = now - RETENTION
    if not accounts.exists():
        return
    for folder in accounts.iterdir():
        if not re.fullmatch(r'[a-f0-9]{64}', folder.name):
            continue
        safe_directory(folder)
        current = read_folder(folder)
        name = current['run'] if current else None
        if current:
            orders = []
            expired = False
            for order in current['orders']:
                remaining = [s for s in order['sources'] if s['timestamp'] >= cutoff]
                expired |= len(remaining) != len(order['sources'])
                if remaining:
                    order['sources'] = remaining
                    orders.append(order)
            state = current['state']
            for key in ('seen_messages', 'seen_orders'):
                retained = {k: v for k, v in state[key].items() if v >= cutoff}
                expired |= len(retained) != len(state[key])
                state[key] = retained
            if expired:
                metadata = {'generated_at': now, 'messages_read': 0, 'new_orders': 0}
                name, _ = publish_snapshot(folder, now, state, orders, metadata)
        clean_snapshots(folder, name, cutoff)


def config_digest(preferences, allowlist):
    # Include rule source so changes also cause the report to be reclassified.
    payload = json.dumps([preferences, allowlist, RETENTION], ensure_ascii=True, sort_keys=True)
    return hashlib.sha256(payload.encode() + (ROOT / 'src' / 'filter_rules.py').read_bytes()
                          + (ROOT / 'src' / 'user_settings.py').read_bytes()
                          + (ROOT / 'config' / 'extraction_dictionary.json').read_bytes()).hexdigest()


def load_preferences():
    preferences = json.loads((ROOT / 'config' / 'tutor_preferences.json').read_text(encoding='utf-8'))
    profile_path = ROOT / 'config' / 'tutor_profile.json'
    if profile_path.exists():
        preferences['tutor_profile'] = json.loads(profile_path.read_text(encoding='utf-8'))
    elif preferences.get('tutor_profile_required'):
        raise RuntimeError('TUTOR_PROFILE_NOT_CONFIGURED')
    resume_path = ROOT / 'config' / 'tutor_resume.txt'
    if resume_path.exists():
        preferences.setdefault('tutor_profile', {})['resume'] = resume_path.read_text(encoding='utf-8')
    return apply_user_settings(preferences, load_user_settings(ROOT / 'manual_closed_orders.json'))


def load_manual_closed(path):
    return load_user_settings(path)['closed_order_keys']


def run_once(private_root, now, *, reader=None, account=None, preferences=None, allowlist=None, commute_client=None):
    preferences = preferences if preferences is not None else load_preferences()
    allowlist = allowlist if allowlist is not None else json.loads((ROOT / 'config' / 'chat_allowlist.json').read_text(encoding='utf-8'))
    use_local_source = reader is None
    if account is None:
        _, _, account = detect_account(load_upstream())
    if use_local_source:
        reader = lambda allow, start, end, path: read_messages(allow, start, end, path, expected_account=account)
    root = safe_directory(private_root)
    now = int(now)
    with run_lock(root):
        folder = account_root(root, account)
        temporary = safe_directory(root / 'temporary')
        for child in temporary.iterdir():
            if child.is_dir() and re.fullmatch(r'decrypt-[a-zA-Z0-9_-]+', child.name):
                remove_owned_directory(child, temporary, r'decrypt-[a-zA-Z0-9_-]+')
        previous = read_current(root, account)
        old_state = previous['state'] if previous else {'success_at': now - RETENTION, 'seen_messages': {}, 'seen_orders': {}}
        if old_state['success_at'] > now:
            raise RuntimeError('CLOCK_MOVED_BACKWARD')
        start = old_state['success_at'] - 600 if previous else now - RETENTION
        digest = config_digest(preferences, allowlist)
        changed = bool(previous and old_state.get('config_digest') != digest)
        if changed:
            start = min(start, now - RETENTION)
        start = max(start, now - RETENTION)
        messages = reader(allowlist, start, now, temporary)
        # Validate the adapter boundary again before parsing or persisting.
        for message in messages:
            if message['group_name'] not in allowlist['allowed_group_names']:
                raise PermissionError('CHAT_NOT_ALLOWED')
            if not start <= message['timestamp'] <= now or not message['id']:
                raise IncompleteReadError('MESSAGE_OUTSIDE_QUERY')
        cutoff = now - RETENTION
        seen = {key: value for key, value in old_state['seen_messages'].items() if value >= cutoff}
        if changed:
            seen = {}  # Replay the retained seven days after a rules change.
        known_orders = {key: value for key, value in old_state['seen_orders'].items() if value >= cutoff}
        orders = []
        reread_ids = {message['id'] for message in messages} if changed else set()
        for order in previous['orders'] if previous else []:
            if not all(s['group_name'] in allowlist['allowed_group_names'] for s in order['sources']):
                continue
            retained = [s for s in order['sources'] if s['timestamp'] >= cutoff and s['id'] not in reread_ids]
            if retained:
                for source in retained:
                    cached_message = {**source, 'type': order['type'], 'content': order['raw']}
                    orders.extend(classify_order(child, preferences) for child in extract_orders(cached_message))
        new_ids, ignored = set(), 0
        for message in messages:
            if message['id'] in seen:
                continue
            seen[message['id']] = message['timestamp']
            if message['timestamp'] < cutoff:
                continue
            extracted = extract_orders(message)
            ignored += int(not extracted)
            for order in extracted:
                classified = classify_order(order, preferences)
                orders.append(classified)
                fingerprint = classified['fingerprint']
                if fingerprint not in known_orders:
                    new_ids.add(fingerprint)
                known_orders[fingerprint] = max(message['timestamp'], known_orders.get(fingerprint, 0))
        orders = merge_orders(orders)
        orders = [order for order in orders if order['type'] != 1 or any(
            order['fields'].get(key) for key in
            ('grade', 'subjects', 'hourly_cny', 'schedule', 'address', 'teacher_requirements'))]
        if commute_client is not None:
            from .commute import enrich_prioritized
            orders = enrich_prioritized(orders, preferences, commute_client, now)
        counts = {status: sum(o['status'] == status or status == 'rejected' and o['status'] == 'closed' for o in orders) for status in LABELS}
        metadata = {'generated_at': now, 'messages_read': len(messages), 'new_orders': len(new_ids),
                    'ignored_messages': ignored, 'counts': counts, 'configuration_changed': changed,
                    'map_check_enabled': commute_client is not None}
        metadata['closed_order_keys'] = sorted(set(preferences.get('closed_order_keys', []) + preferences.get('closed_order_ids', [])))
        metadata['preferred_address_keywords'] = preferences.get('preferred_address_keywords', [])
        metadata['ui_preferences'] = preference_snapshot(preferences)
        metadata['rejection_feedback'] = preferences.get('rejection_feedback', [])
        metadata['preference_overrides'] = preferences.get('user_preference_overrides', {})
        metadata['preference_context'] = {'出发地点': preferences['commute']['origin'],
            '城市与交通': preferences['commute']['city'] + ' · 公共交通（含步行、换乘）',
            '每日计划': '、'.join(preferences.get('daily_run', {}).get('local_times', [])),
            '订单范围': '发布于运行前7天内；本地订单保留7天', '设置生效': '保存后下次筛选生效；未知条件保留待确认'}
        state = {'success_at': now, 'seen_messages': {k: v for k, v in seen.items() if v >= cutoff},
                 'seen_orders': known_orders, 'config_digest': digest}
        name, report = publish_snapshot(folder, now, state, orders, metadata)
        metadata.update(status='OK', report=report)
        try:
            clean_all_accounts(root, now)
        except Exception:
            metadata['cleanup_pending'] = True
        return metadata


def main():
    root = Path(os.environ['LOCALAPPDATA']) / 'WeChatTutorFilter'
    try:
        preferences = load_preferences()
        commute_client = None
        map_unavailable = False
        no_map = '--no-map' in sys.argv
        if preferences['commute'].get('automatic_query_enabled') and not no_map:
            from .commute import MapClient, MapError
            try:
                commute_client = MapClient(root, city=preferences['commute']['city'], origin=preferences['commute']['origin'])
            except MapError:
                map_unavailable = True
        result = run_once(root, int(time.time()), preferences=preferences, commute_client=commute_client)
        if map_unavailable:
            result['map_unavailable'] = True
        if no_map:
            result['map_skipped'] = True
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except Exception as exc:
        # Exception text can contain private paths/SQL/content; never print it.
        code = str(exc) if isinstance(exc, (IncompleteReadError, RunBusyError)) else 'RUN_FAILED'
        print(json.dumps({'status': 'FAILED', 'reason': code, 'error_type': type(exc).__name__}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
