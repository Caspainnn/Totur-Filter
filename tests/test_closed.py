import copy
import unittest
import json
import tempfile
from pathlib import Path
from src.run_filter import load_manual_closed
from tests.test_rules import PREF, result
from src.filter_rules import classify_order, extract_orders
from src.commute import enrich_order


class ClosedOrderTests(unittest.TestCase):
    def test_saved_closed_file_is_read_and_invalid_keys_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'manual_closed_orders.json'
            self.assertEqual(load_manual_closed(path), [])
            path.write_text(json.dumps({'closed_order_keys': ['BJ999001', 'BJ999001']}), encoding='utf-8')
            self.assertEqual(load_manual_closed(path), ['BJ999001'])
            path.write_text(json.dumps({'closed_order_keys': ['<script>']}), encoding='utf-8')
            with self.assertRaises(RuntimeError):
                load_manual_closed(path)

    def test_confirmed_closed_id_wins_and_skips_maps(self):
        preferences = copy.deepcopy(PREF)
        preferences['closed_order_ids'] = ['BJ999001']
        message = {'id': 'fixture', 'group_name': '测试群', 'timestamp': 100,
                   'type': 1, 'content': '编号：👑BJ999001\n五年级数学120元/小时\n地址：线上'}
        order = classify_order(extract_orders(message)[0], preferences)
        self.assertEqual(order['status'], 'closed')
        class Forbidden:
            def commute(self, *args):
                raise AssertionError('Closed orders must not query maps')
        self.assertEqual(enrich_order(order, preferences, Forbidden(), 100)['status'], 'closed')
        message['content'] = message['content'].replace('BJ999001', 'BJ9990012')
        self.assertNotEqual(classify_order(extract_orders(message)[0], preferences)['status'], 'closed')
