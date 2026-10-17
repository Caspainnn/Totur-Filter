"""Remove expired application snapshots offline; never read WeChat or query maps."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.run_filter import RETENTION, clean_all_accounts, run_lock, safe_directory


def inspect(root, now):
    counts = {'snapshots': 0, 'expired_snapshots': 0, 'expired_sources': 0}
    accounts = root / 'accounts'
    if not accounts.exists():
        return counts
    safe_directory(accounts)
    for account in accounts.iterdir():
        if not re.fullmatch(r'[a-f0-9]{64}', account.name):
            continue
        safe_directory(account)
        for snapshot in account.iterdir():
            if not re.fullmatch(r'run-\d+-[a-f0-9]{32}', snapshot.name):
                continue
            safe_directory(snapshot)
            counts['expired_snapshots'] += int(snapshot.name.split('-')[1]) < now-RETENTION
            path = snapshot / 'orders.json'
            if path.is_symlink():
                raise RuntimeError('CLEANUP_LINK_REFUSED')
            if path.exists():
                orders = json.loads(path.read_text(encoding='utf-8'))
                counts['snapshots'] += 1
                counts['expired_sources'] += sum(s['timestamp'] < now-RETENTION for o in orders for s in o['sources'])
    return counts


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    root = Path(os.environ['LOCALAPPDATA']) / 'WeChatTutorFilter'
    now = int(time.time())
    if args.apply:
        with run_lock(root):
            before = inspect(root, now)
            clean_all_accounts(root, now)
            after = inspect(root, now)
    else:
        before = after = inspect(root, now)
    print(json.dumps({'applied': args.apply, 'retention_days': 7, 'before': before, 'after': after}))
