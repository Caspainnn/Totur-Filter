import unittest

from src.filter_rules import extract_orders, classify_order
from src.report import render_key_information
from tests.test_rules import PREF


FIRST = '''北京线下
北京初三女生数学，数学成绩比较好的老师，也能顺手辅导一下物理物理，住朝阳区太阳宫太阳公元南区
要求：985女生
薪酬：400一次两小时 一周2次的话一次两小时，一周三次的话一次1.5小时'''
SECOND = '''北京线下
北京初二女生全科，理科为主，住昌平高教园
要求：985女生，研究一优先
薪酬：300一次两小时'''


def message(raw):
    return {'id': 'prose', 'timestamp': 100000, 'group_name': '测试群', 'type': 1, 'content': raw}


class ProseBatchTests(unittest.TestCase):
    def test_repeated_headers_split_without_ids(self):
        for separator in ['\n', '\n\n\n', '\r\n \r\n']:
            orders = extract_orders(message('sender:\n' + FIRST + separator + SECOND))
            self.assertEqual(len(orders), 2)
            first, second = [classify_order(o, PREF) for o in orders]
            self.assertEqual([first['fields']['grade'], second['fields']['grade']], [9, 8])
            self.assertNotIn('300', first['raw'])
            self.assertNotIn('400', second['raw'])
            self.assertNotEqual(first['fingerprint'], second['fingerprint'])
            self.assertEqual(first['raw'].count('北京线下'), 1)

    def test_blank_lines_split_complete_prose_offers_without_headers(self):
        raw = FIRST.split('\n', 1)[1] + '\n\n' + SECOND.split('\n', 1)[1]
        orders = extract_orders(message(raw))
        self.assertEqual(len(orders), 2)
        self.assertEqual([classify_order(o, PREF)['fields']['grade'] for o in orders], [9, 8])

    def test_unsplit_headers_fail_before_rejection(self):
        raw = FIRST + '\n' + SECOND
        result = classify_order({'raw': raw, 'type': 1, 'sources': [message(raw)]}, PREF)
        self.assertEqual(result['status'], 'parse_failed')
        self.assertEqual(result['fields'], {})
        self.assertNotIn('feedback-reject', render_key_information(result, '', ''))

    def test_single_offer_with_field_spacing_remains_whole(self):
        self.assertEqual(len(extract_orders(message(FIRST.replace('\n', '\n\n')))), 1)
