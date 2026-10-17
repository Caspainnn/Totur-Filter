import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from src.run_filter import run_once, read_current, RunBusyError
from src.report import render_report

ROOT = Path(__file__).resolve().parents[1]
PREF = json.loads((ROOT / 'tests/fixtures/preferences.json').read_text(encoding='utf-8'))
ALLOW = json.loads((ROOT / 'tests/fixtures/allowlist.json').read_text(encoding='utf-8'))


def message(mid='id1', text='初一数学 100元/小时', at=100000):
    return {'id': mid, 'group_name': ALLOW['allowed_group_names'][0], 'timestamp': at, 'type': 1, 'content': text}


class RunTests(unittest.TestCase):
    def test_first_read_includes_day_six_and_report_omits_day_eight(self):
        now = 10 * 86400
        with tempfile.TemporaryDirectory() as folder:
            def reader(allow, start, end, temporary):
                self.assertEqual(start, now-7*86400)
                return [message(at=now-6*86400)]
            result=run_once(Path(folder),now,reader=reader,account='fixture',preferences=PREF,allowlist=ALLOW)
            self.assertEqual(sum(result['counts'].values()),1)
        order={'status':'needs_confirmation','raw':'EXPIRED_RAW_MARKER','fields':{},'reasons':[],
               'sources':[{'id':'old','group_name':'fixture','timestamp':now-8*86400}],'fingerprint':'old'}
        html=render_report([order],{'generated_at':now,'new_orders':0,'messages_read':0})
        self.assertNotIn('EXPIRED_RAW_MARKER',html)

    def test_first_range_and_overlap_duplicate(self):
        ranges = []
        def reader(allow, start, end, path):
            ranges.append((start, end))
            return [message()]
        with tempfile.TemporaryDirectory() as folder:
            first = run_once(Path(folder), 100000, reader=reader, account='fixture', preferences=PREF, allowlist=ALLOW)
            second = run_once(Path(folder), 100100, reader=reader, account='fixture', preferences=PREF, allowlist=ALLOW)
            self.assertEqual(ranges, [(100000 - 7 * 86400, 100000), (99400, 100100)])
            self.assertEqual(first['new_orders'], 1)
            self.assertEqual(second['new_orders'], 0)
            self.assertEqual(second['counts']['needs_confirmation'], 1)

    def test_read_failure_does_not_advance(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run_once(root, 100000, reader=lambda *args: [message()], account='fixture', preferences=PREF, allowlist=ALLOW)
            with self.assertRaises(RuntimeError):
                run_once(root, 100100, reader=lambda *args: (_ for _ in ()).throw(RuntimeError('fixture')), account='fixture', preferences=PREF, allowlist=ALLOW)
            self.assertEqual(read_current(root, 'fixture')['state']['success_at'], 100000)

    def test_reclassifies_saved_candidates_after_preference_change(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run_once(root, 100000, reader=lambda *args: [message()], account='fixture', preferences=PREF, allowlist=ALLOW)
            stricter = json.loads(json.dumps(PREF))
            stricter['pay']['minimum_hourly_cny'] = 150
            report = run_once(root, 100100, reader=lambda *args: [], account='fixture', preferences=stricter, allowlist=ALLOW)
            self.assertEqual(report['counts']['rejected'], 1)

    def test_html_content_escaped_without_external_resources(self):
        order = {'status': 'needs_confirmation', 'raw': '<script>alert(1)</script>', 'fields': {}, 'reasons': ['待确认'],
                 'sources': [{'id': 'x', 'group_name': '<测试群>', 'timestamp': 100000}], 'fingerprint': 'x'}
        html = render_report([order], {'generated_at': 100000, 'new_orders': 1, 'messages_read': 1})
        self.assertIn('&lt;script&gt;', html)
        self.assertNotIn('<script>', html)
        self.assertNotIn('src="http', html)

    def test_atomic_pointer_failure_preserves_previous(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run_once(root, 100000, reader=lambda *args: [message()], account='fixture', preferences=PREF, allowlist=ALLOW)
            with patch('src.run_filter.os.replace', side_effect=OSError('fixture')):
                with self.assertRaises(OSError):
                    run_once(root, 100100, reader=lambda *args: [], account='fixture', preferences=PREF, allowlist=ALLOW)
            self.assertEqual(read_current(root, 'fixture')['state']['success_at'], 100000)

    def test_busy_lock_rejects_second_run(self):
        from src.run_filter import run_lock
        with tempfile.TemporaryDirectory() as folder:
            with run_lock(Path(folder)):
                with self.assertRaises(RunBusyError):
                    run_once(Path(folder), 100000, reader=lambda *args: [], account='fixture', preferences=PREF, allowlist=ALLOW)

    def test_7_day_retention_and_account_isolation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run_once(root, 100000, reader=lambda *args: [message()], account='fixture', preferences=PREF, allowlist=ALLOW)
            other = run_once(root, 100100, reader=lambda *args: [], account='other', preferences=PREF, allowlist=ALLOW)
            self.assertEqual(sum(other['counts'].values()), 0)
            late = run_once(root, 100000 + 8 * 86400, reader=lambda *args: [], account='fixture', preferences=PREF, allowlist=ALLOW)
            self.assertEqual(sum(late['counts'].values()), 0)
            self.assertEqual(read_current(root, 'fixture')['state']['seen_messages'], {})

    def test_reader_returning_unapproved_group_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            wrong = message()
            wrong['group_name'] = '未知群'
            with self.assertRaises(PermissionError):
                run_once(Path(folder), 100000, reader=lambda *args: [wrong], account='fixture', preferences=PREF, allowlist=ALLOW)

    def test_historical_snapshots_and_inactive_account_raw_expire(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first = run_once(root, 100000, reader=lambda *args: [message()], account='fixture', preferences=PREF, allowlist=ALLOW)
            copied = run_once(root, 100000 + 6 * 86400, reader=lambda *args: [], account='fixture', preferences=PREF, allowlist=ALLOW)
            run_once(root, 100000 + 8 * 86400, reader=lambda *args: [], account='other', preferences=PREF, allowlist=ALLOW)
            self.assertFalse(Path(first['report']).exists())
            self.assertFalse(Path(copied['report']).exists())
            self.assertEqual(read_current(root, 'fixture')['orders'], [])

    def test_orders_and_dedup_expire_after_seven_days(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run_once(root, 100000, reader=lambda *args: [message()], account='fixture', preferences=PREF, allowlist=ALLOW)
            boundary = run_once(root, 100000 + 7 * 86400, reader=lambda *args: [], account='fixture', preferences=PREF, allowlist=ALLOW)
            self.assertEqual(sum(boundary['counts'].values()), 1)
            expired = run_once(root, 100000 + 7 * 86400 + 1, reader=lambda *args: [], account='fixture', preferences=PREF, allowlist=ALLOW)
            self.assertEqual(sum(expired['counts'].values()), 0)
            self.assertFalse(read_current(root, 'fixture')['state']['seen_messages'])

    def test_commute_enrichment_rechecks_existing_orders(self):
        class FixedMap:
            def commute(self, *args):
                return {'status': 'ok', 'minutes': 45, 'verified_schedule': True}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            text = '初一数学100元/小时\n地址：测试小区\n时间：周三18:00'
            run_once(root, 100000, reader=lambda *args: [message(text=text)], account='fixture', preferences=PREF, allowlist=ALLOW)
            result = run_once(root, 100100, reader=lambda *args: [], account='fixture', preferences=PREF, allowlist=ALLOW, commute_client=FixedMap())
            self.assertEqual(result['counts']['recommended'], 1)

    def test_same_physical_parent_alias_not_rejected(self):
        from src.run_filter import account_root
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run_once(root, 100000, reader=lambda *args: [message()], account='fixture', preferences=PREF, allowlist=ALLOW)
            base = account_root(root, 'fixture')
            (base.parent / 'alias').mkdir()
            real_resolve = Path.resolve
            def aliased_resolve(path, *args, **kwargs):
                if path.name.startswith('run-'):
                    return base.parent / 'alias' / '..' / base.name / path.name
                return real_resolve(path, *args, **kwargs)
            with patch.object(Path, 'resolve', aliased_resolve):
                self.assertEqual(read_current(root, 'fixture')['state']['success_at'], 100000)

    def test_legacy_cached_batch_replaced_by_individual_orders(self):
        from src.run_filter import account_root, publish_snapshot
        raw = '编号：BJ990001\n年级科目：初一数学\n薪酬：120/h\n编号：BJ990002\n年级科目：初二数学\n薪酬：90元/3小时/次课'
        for reread in (True, False):
            with self.subTest(reread=reread), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                source = {'id': 'id1', 'group_name': ALLOW['allowed_group_names'][0], 'timestamp': 100000}
                legacy = {'raw': raw, 'type': 1, 'sources': [source], 'fingerprint': 'legacy', 'status': 'needs_confirmation', 'fields': {}, 'reasons': []}
                state = {'success_at': 100000, 'seen_messages': {'id1': 100000}, 'seen_orders': {'legacy': 100000}, 'config_digest': 'old'}
                publish_snapshot(account_root(root, 'fixture'), 100000, state, [legacy], {'generated_at': 100000, 'messages_read': 1, 'new_orders': 1})
                reader = lambda *args: [message(text=raw)] if reread else []
                run_once(root, 100100, reader=reader, account='fixture', preferences=PREF, allowlist=ALLOW)
                orders = read_current(root, 'fixture')['orders']
                self.assertEqual(len(orders), 2)
                self.assertEqual(sorted(o['fields']['hourly_cny'][0] for o in orders), [30, 120])


if __name__ == '__main__':
    unittest.main()
