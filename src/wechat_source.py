"""Only allowed group queries; local keys never persisted. No UI imports."""
import contextlib
import hashlib
import hmac
import importlib.util
import io
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import struct
import sys
import tempfile
import types

ROOT = Path(__file__).resolve().parents[1]


class IncompleteReadError(RuntimeError):
    """Public errors are non-sensitive reason codes only."""


def require_allowed(group_id, allowed_ids):
    if not isinstance(group_id, str) or not group_id.endswith('@chatroom') or group_id not in allowed_ids:
        raise PermissionError('CHAT_NOT_ALLOWED')


def resolve_groups(conn, names):
    if not names or any(not isinstance(n, str) or not n for n in names) or len(set(names)) != len(names):
        raise IncompleteReadError('INVALID_ALLOWLIST')
    resolved = {}
    for name in names:
        rows = conn.execute("SELECT username FROM contact WHERE nick_name=? AND username LIKE '%@chatroom'", (name,)).fetchall()
        ids = {row[0] for row in rows}
        if len(ids) != 1:
            raise IncompleteReadError('GROUP_NOT_UNIQUE')
        group = ids.pop()
        if group in resolved:
            raise IncompleteReadError('DUPLICATE_GROUP_ID')
        resolved[group] = name
    return resolved


def decode_text(value):
    if value is None:
        return ''
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        try:
            if value.startswith(b'\x28\xb5\x2f\xfd'):
                import zstandard
                value = zstandard.ZstdDecompressor().decompress(value, max_output_size=4 * 1024 * 1024)
            return value.decode('utf-8')
        except Exception:
            return ''
    return ''


def query_group(shards, group, name, start, end, limit=100000):
    if not isinstance(group, str) or not group.endswith('@chatroom') or start > end or limit < 1:
        raise IncompleteReadError('INVALID_QUERY')
    table = 'Msg_' + hashlib.md5(group.encode()).hexdigest()
    messages = []
    try:
        for label, conn in shards:
            if not conn.execute('SELECT 1 FROM sqlite_master WHERE type=\'table\' AND name=?', (table,)).fetchone():
                continue
            columns = {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
            needed = {'local_id', 'server_id', 'local_type', 'create_time', 'message_content'}
            if not needed <= columns:
                raise IncompleteReadError('MESSAGE_SCHEMA_UNSUPPORTED')
            compressed = 'compress_content' if 'compress_content' in columns else 'NULL'
            sql = f'SELECT local_id,server_id,local_type,create_time,message_content,{compressed} FROM {table} WHERE create_time>=? AND create_time<=? ORDER BY create_time,local_id LIMIT ?'
            for local_id, server_id, kind, timestamp, content, cc in conn.execute(sql, (start, end, limit + 1)):
                if len(messages) >= limit:
                    raise IncompleteReadError('MESSAGE_LIMIT_REACHED')
                identity = f'{group}:server:{server_id}' if server_id else f'{group}:shard:{label}:{local_id}'
                if local_id is None or timestamp is None:
                    raise IncompleteReadError('MISSING_MESSAGE_ID')
                text = decode_text(content) or decode_text(cc)
                messages.append({'id': hashlib.sha256(identity.encode()).hexdigest(), 'group_name': name,
                                 'timestamp': int(timestamp), 'type': int(kind), 'content': text})
    except sqlite3.Error:
        raise IncompleteReadError('SHARD_QUERY_FAILED') from None
    return sorted(messages, key=lambda m: (m['timestamp'], m['id']))


def load_upstream():
    path = ROOT / 'vendor' / 'wechat_db.py'
    provenance = json.loads((ROOT / 'vendor' / 'PROVENANCE.json').read_text(encoding='utf-8-sig'))
    if hashlib.sha256(path.read_bytes()).hexdigest() != provenance['sha256']:
        raise IncompleteReadError('DEPENDENCY_CHECKSUM_MISMATCH')
    # The standalone module imports only this logger from the original package.
    # A quiet logger shim avoids importing the original package's UI/send code.
    shim = types.ModuleType('wechatauto.logger')
    shim.wxlog = logging.getLogger('tutor.db')
    shim.wxlog.handlers = [logging.NullHandler()]
    shim.wxlog.propagate = False
    previous = sys.modules.get('wechatauto.logger')
    sys.modules['wechatauto.logger'] = shim
    try:
        spec = importlib.util.spec_from_file_location('tutor_vendor_db', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if previous is None:
            sys.modules.pop('wechatauto.logger', None)
        else:
            sys.modules['wechatauto.logger'] = previous


def detect_account(upstream):
    root = upstream.auto_detect_db_dir()
    if not root:
        raise IncompleteReadError('DATA_DIRECTORY_NOT_FOUND')
    accounts = upstream._find_account_dirs(root)
    if len(accounts) != 1:
        raise IncompleteReadError('ACCOUNT_SELECTION_REQUIRED')
    account = os.path.basename(accounts[0])
    identity = hashlib.sha256((str(Path(root).resolve()) + ':' + account).encode()).hexdigest()
    return root, account, identity


def verify_snapshot(stamp_path, wal_exists, validated_empty_wal=False):
    try:
        parts = Path(stamp_path).read_text().split(',')
        applied = int(parts[5])
        wal_size = int(parts[4])
        if applied < 0 or (wal_exists and wal_size > 32 and applied == 0 and not validated_empty_wal):
            raise ValueError
    except (OSError, ValueError, IndexError):
        raise IncompleteReadError('WAL_SNAPSHOT_INCOMPLETE') from None


def verify_source_identity(expected_account, actual_account, before, after):
    if expected_account != actual_account:
        raise IncompleteReadError('ACCOUNT_CHANGED_DURING_READ')
    if before != after:
        raise IncompleteReadError('SHARD_MANIFEST_CHANGED')


def merge_wal_strict(dst, wal_path, key, source_salt, decrypt_page):
    """Authenticate current-generation pages; apply committed transactions only.

    Unlike the vendor merge, no current frame is skipped on a page-byte heuristic.
    References: sqlite.org/fileformat2.html#wal_format; SQLCipher SHA512 page HMAC.
    """
    details = Path(wal_path).stat()
    if details.st_size > 512 * 1024 * 1024:
        raise IncompleteReadError('WAL_TOO_LARGE')
    data = Path(wal_path).read_bytes()
    if len(data) < 32:
        raise IncompleteReadError('WAL_HEADER_INCOMPLETE')
    magic, version, page_size = struct.unpack('>III', data[:12])
    if magic not in (0x377F0682, 0x377F0683) or version != 3007000 or page_size != 4096:
        raise IncompleteReadError('WAL_FORMAT_UNSUPPORTED')
    salt = data[16:24]
    raw_key = key[:32]
    db_salt = key[32:] if len(key) == 48 else source_salt
    if len(db_salt) != 16:
        raise IncompleteReadError('WAL_AUTH_PARAMETERS_INVALID')
    mac_key = hashlib.pbkdf2_hmac('sha512', raw_key, bytes(v ^ 0x3A for v in db_salt), 2, dklen=32)
    pending, committed = {}, {}
    applied, db_size, current_frames = 0, 0, 0
    frame_count = (len(data) - 32) // 4120
    for index in range(frame_count):
        offset = 32 + index * 4120
        hdr, page = data[offset:offset + 24], data[offset + 24:offset + 4120]
        if hdr[8:16] != salt:
            break  # Old-generation trailing frames after a WAL reset are not data.
        current_frames += 1
        pgno, commit_size = struct.unpack('>II', hdr[:8])
        if not 1 <= pgno <= 1000000 or commit_size > 1000000:
            raise IncompleteReadError('WAL_PAGE_NUMBER_INVALID')
        payload = page[16 if pgno == 1 else 0:4032] + struct.pack('<I', pgno)
        if not hmac.compare_digest(hmac.new(mac_key, payload, hashlib.sha512).digest(), page[4032:]):
            raise IncompleteReadError('WAL_FRAME_AUTH_FAILED')
        plain = decrypt_page(key, page, pgno)
        if len(plain) != 4096:
            raise IncompleteReadError('WAL_DECRYPT_FAILED')
        pending[pgno] = plain
        if commit_size:
            committed.update(pending)
            pending.clear()
            applied, db_size = index + 1, commit_size
    if current_frames and not applied:
        raise IncompleteReadError('WAL_NO_COMMITTED_SNAPSHOT')
    after = Path(wal_path).stat()
    if (details.st_size, details.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise IncompleteReadError('WAL_CHANGED_DURING_READ')
    if applied:
        with Path(dst).open('r+b') as output:
            for pgno, plain in committed.items():
                if pgno <= db_size:
                    output.seek((pgno - 1) * 4096)
                    output.write(plain)
            output.truncate(db_size * 4096)
            output.seek(28)
            output.write(struct.pack('>I', db_size))
    return applied


def read_messages(allowlist, start, end, private_root, *, expected_account=None):
    if (not allowlist.get('require_unique_exact_match') or allowlist.get('allow_private_chats')
            or allowlist.get('upload_chat_content') or allowlist.get('persist_database_keys')
            or allowlist.get('log_message_content')):
        raise IncompleteReadError('UNSAFE_CONFIGURATION')
    upstream = load_upstream()
    root, account, identity = detect_account(upstream)
    if expected_account is not None:
        verify_source_identity(expected_account, identity, set(), set())

    class StrictDB(upstream.WeChatDB):
        def _collect_db_files(self):
            return [entry for entry in super()._collect_db_files()
                    if os.path.basename(entry[1]) == 'contact.db'
                    or re.match(r'^message[/\\]message_\d+\.db$', entry[0])]

        def _load_or_extract_keys(self, master_key=None):
            self._keys = self.extract_keys()
            if not self._db_files or len(self._keys) != len(self._db_files):
                raise IncompleteReadError('DATABASE_KEYS_UNAVAILABLE')

        def _save_keys(self):
            pass

        def _auto_diagnose_key_failure(self, rel):
            pass

        def _merge_wal(self, dst, wal_path, key, from_frame):
            with open(wal_path[:-4], 'rb') as source:
                source_salt = source.read(16)
            try:
                applied = merge_wal_strict(dst, wal_path, key, source_salt, upstream._decrypt_page)
                if applied == 0:
                    if not hasattr(self, '_validated_empty_wals'):
                        self._validated_empty_wals = set()
                    self._validated_empty_wals.add(wal_path)
                return applied
            except IncompleteReadError as exc:
                self._wal_failure_reason = str(exc)
                raise

        def _open_unlocked(self, rel):
            conn = super()._open_unlocked(rel)
            try:
                stamp = Path(self.workdir) / (rel.replace(os.sep, '__') + '.stamp')
                try:
                    wal_path = self._wal_path(rel)
                    verify_snapshot(stamp, bool(wal_path), wal_path in getattr(self, '_validated_empty_wals', set()))
                except IncompleteReadError:
                    raise IncompleteReadError(getattr(self, '_wal_failure_reason', 'WAL_SNAPSHOT_INCOMPLETE')) from None
                # No previous snapshot is present in a new unique temp directory.
                conn.execute('PRAGMA query_only=ON')
                return conn
            except Exception:
                conn.close()
                raise

    private_root = Path(private_root)
    private_root.mkdir(parents=True, exist_ok=True)
    connections = []
    try:
        with tempfile.TemporaryDirectory(prefix='decrypt-', dir=private_root) as work:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                db = StrictDB(db_dir=root, account=account, workdir=work)
                try:
                    manifest = {rel for rel, _, _ in db._db_files}
                    contact = next((rel for rel, _, _ in db._db_files if os.path.basename(rel) == 'contact.db'), None)
                    if contact is None:
                        raise IncompleteReadError('CONTACT_DATABASE_MISSING')
                    conn = db._open(contact)
                    try:
                        allowed = resolve_groups(conn, allowlist['allowed_group_names'])
                    finally:
                        conn.close()
                    for rel, _, _ in db._db_files:
                        if re.match(r'^message[/\\]message_\d+\.db$', rel):
                            connections.append((rel, db._open(rel)))
                    if not connections:
                        raise IncompleteReadError('MESSAGE_SHARDS_MISSING')
                    messages = []
                    for group, name in allowed.items():
                        require_allowed(group, allowed)
                        messages.extend(query_group(connections, group, name, start, end))
                    _, _, final_identity = detect_account(upstream)
                    final_manifest = {rel for rel, _, _ in db._collect_db_files()}
                    verify_source_identity(identity, final_identity, manifest, final_manifest)
                    return messages
                finally:
                    for _, conn in connections:
                        conn.close()
                    db._keys.clear()
    except IncompleteReadError:
        raise
    except Exception:
        raise IncompleteReadError('LOCAL_READ_FAILED') from None
