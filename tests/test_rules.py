import json
from pathlib import Path
import unittest
from src.filter_rules import extract_orders, classify_order, merge_orders

PREF = json.loads((Path(__file__).resolve().parents[1] / 'tests/fixtures/preferences.json').read_text(encoding='utf-8'))


def result(text, kind=1):
    orders = extract_orders({'id': 'fixture', 'group_name': '测试群', 'timestamp': 100, 'type': kind, 'content': text})
    return classify_order(orders[0], PREF)


class RuleTests(unittest.TestCase):
    def test_number_dedup_keeps_latest_fields_and_source(self):
        orders = []
        for timestamp, pay, sender in [(100, 120, 'sender-a'), (200, 150, 'sender-b')]:
            raw = f'{sender}:\n家教编号：990000001-1\n年级：四年级\n科目：语文\n报酬：{pay}/h'
            message = {'id': str(timestamp), 'group_name': '测试群', 'timestamp': timestamp, 'type': 1, 'content': raw}
            orders.extend(classify_order(order, PREF) for order in extract_orders(message))
        merged = merge_orders(orders)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['fields']['hourly_cny'], [150, 150])
        self.assertEqual([s['timestamp'] for s in merged[0]['sources']], [200])
        self.assertIn('sender-b', merged[0]['raw'])
    def test_amount_before_hourly_salary_label(self):
        for pay, expected in [('100时薪', [100, 100]), ('80-120时薪', [80, 120]), ('100元时薪', [100, 100])]:
            with self.subTest(pay=pay):
                order = result('五年级数学\n【辅导时薪】：' + pay)
                self.assertEqual(order['fields']['hourly_cny'], expected)
                self.assertNotIn('价格单位或金额待确认', order['reasons'])
    def test_primary_companion_passes_subject_filter(self):
        for subject in ('陪伴', '陪读'):
            order = result('二年级' + subject + '120元/小时')
            self.assertEqual(order['fields']['subjects'], ['小学陪伴'])
            self.assertNotIn('科目待确认', order['reasons'])
            self.assertNotEqual(order['status'], 'rejected')
        self.assertIn('科目待确认', result('初一陪伴120元/小时')['reasons'])
    def test_unspecified_time_is_negotiable(self):
        for schedule in ('一周1-2次。商量。2小时。', '一周1-2次', '具体协商', ''):
            with self.subTest(schedule=schedule):
                order = result('初一数学120元/小时\n辅导时间：' + schedule)
                self.assertEqual(order['fields']['time_status'], 'ok')
                self.assertNotIn('上课时间待确认', order['reasons'])
    def test_real_pending_schedule_formats(self):
        for schedule in ('一周1次，周日下午', '一周一次，周日', '一周一次，固定周四晚上7-9点',
                         '一周2次 周一周四晚上6-8点', '周一，周三晚上18点到19点30',
                         '一周3次，周一三五放学后6.30-7.30',
                         '两周一次2h；周二晚上7点'):
            with self.subTest(schedule=schedule):
                reasons = result('初一数学120元/小时\n时间：' + schedule)['reasons']
                self.assertNotIn('上课时间待确认', reasons)
                self.assertNotIn('上课时间冲突', reasons)
        self.assertIn('上课时间冲突', result('初一数学120元/小时\n时间：周一二三下午4-6点')['reasons'])
        self.assertNotIn('上课时间待确认', result('初一数学120元/小时\n时间：一周2次，每次2小时')['reasons'])
        self.assertIn('上课时间待确认', result('初一数学120元/小时\n时间：每周一，与周三的五点半后的时间')['reasons'])
        self.assertIn('上课时间冲突', result('初一数学120元/小时\n时间：每周一下午3点40—4:40')['reasons'])
    def test_evening_range_and_half_hour(self):
        order = result('六年级全科100元/小时\n时间：周内晚上4次，周一到周四晚6点半~8点半')
        self.assertNotIn('上课时间待确认', order['reasons'])
        self.assertNotIn('上课时间冲突', order['reasons'])
    def test_hourly_pay_units_and_ranges(self):
        cases = [('100-130元/小时', None), ('80-120元/小时', None), ('80-100元/小时', None), ('80-99元/小时', '时薪低于100元'), ('90元/小时', '时薪低于100元'),
                 ('200元/次，每次2小时', None), ('报酬100', '价格单位或金额待确认')]
        for pay, reason in cases:
            with self.subTest(pay=pay):
                r = result('小学三年级数学\n报酬：' + pay)
                if reason:
                    self.assertIn(reason, r['reasons'])
                else:
                    self.assertFalse(any('时薪' in s or '价格' in s or '报价' in s for s in r['reasons']))

    def test_grade_boundaries(self):
        for grade, want in [('小学一年级', 'needs_confirmation'), ('初一', 'needs_confirmation'), ('初二', 'rejected')]:
            self.assertEqual(result(grade + '数学 100元/小时')['status'], want)

    def test_subjects_and_negative_requirement(self):
        self.assertNotIn('科目待确认', result('小学三年级全科 100元/小时')['reasons'])
        self.assertIn('混合科目要求待确认', result('初一数学英语 100元/小时')['reasons'])
        self.assertNotEqual(result('小学三年级语文 100元/小时')['status'], 'rejected')
        self.assertIn('科目待确认', result('小学三年级，不教数学，科目面议 100元/小时')['reasons'])

    def test_primary_mixed_subjects_pass_but_junior_and_unknown_remain_pending(self):
        for grade in ('小学一年级', '小学六年级', '小学'):
            with self.subTest(grade=grade):
                self.assertNotIn('混合科目要求待确认', result(grade + '数学英语 120元/小时')['reasons'])
        for grade in ('初一', ''):
            with self.subTest(grade=grade):
                self.assertIn('混合科目要求待确认', result(grade + '数学英语 120元/小时')['reasons'])

    def test_primary_academic_subjects_and_junior_sciences(self):
        for subject in ('语文', '英语', '语文英语', '数学语文英语'):
            order = result('小学一年级' + subject + ' 120元/小时')
            self.assertFalse(any('科目' in reason for reason in order['reasons']))
        self.assertEqual(result('初一英语 120元/小时')['status'], 'rejected')
        self.assertNotEqual(result('初一数学物理 120元/小时')['status'], 'rejected')
        self.assertEqual(result('小学一年级钢琴 120元/小时')['status'], 'rejected')

    def test_time_conflicts_and_wednesday(self):
        self.assertEqual(result('初一数学 100元/小时\n时间：周一16:00-18:00')['status'], 'rejected')
        self.assertNotIn('上课时间冲突', result('初一数学 100元/小时\n时间：周三上午')['reasons'])
        self.assertNotIn('上课时间待确认', result('初一数学 100元/小时')['reasons'])
        self.assertIn('上课时间待确认', result('初一数学 100元/小时\n时间：周一下午')['reasons'])

    def test_unknown_commute_and_qualifications_not_recommended(self):
        r = result('初一数学 100元/小时\n地点：测试小区\n时间：周三上午\n要求：985大学生')
        self.assertEqual(r['status'], 'needs_confirmation')
        self.assertIn('公共交通通勤未核实', r['reasons'])
        self.assertIn('教师要求需本人确认', r['reasons'])

    def test_multiple_orders_and_image(self):
        msg = {'id': 'm', 'group_name': '测试群', 'timestamp': 100, 'type': 1,
               'content': '订单编号：A001\n初一数学 100元/小时\n订单编号：A002\n初二数学 100元/小时'}
        self.assertEqual(len(extract_orders(msg)), 2)
        self.assertEqual(result('', kind=3)['status'], 'needs_confirmation')

    def test_merge_without_identifier_keeps_sources_and_updates_separate(self):
        a = result('初一数学 100元/小时')
        b = result('初一数学 100元/小时')
        b['sources'][0]['group_name'] = '另一测试群'
        c = result('初一数学 120元/小时')
        merged = merge_orders([a, b, c])
        self.assertEqual(len(merged), 2)
        self.assertEqual(len(merged[0]['sources']), 2)

    def test_clear_chatter_not_order(self):
        self.assertEqual(extract_orders({'id': 'x', 'group_name': '测试群', 'timestamp': 0, 'type': 1, 'content': '大家晚上好'}), [])

    def test_undecodable_text_preserved_as_pending(self):
        orders = extract_orders({'id': 'empty', 'group_name': '测试群', 'timestamp': 0, 'type': 1, 'content': ''})
        self.assertEqual(len(orders), 1)
        self.assertEqual(classify_order(orders[0], PREF)['status'], 'needs_confirmation')

    def test_short_primary_science_not_dropped(self):
        r = result('小三科学 120元/小时')
        self.assertEqual(r['fields']['grade'], 3)
        self.assertEqual(r['status'], 'needs_confirmation')

    def test_alternative_schedule_does_not_reject_possible_day(self):
        r = result('初一数学 100元/小时\n时间：周一16:00或周三上午均可')
        self.assertNotIn('上课时间冲突', r['reasons'])

    def test_numbered_same_grade_orders_split(self):
        msg = {'id': 'multi', 'group_name': '测试群', 'timestamp': 0, 'type': 1,
               'content': '1. 小学三年级数学 80元/小时\n2. 小学三年级数学 150元/小时'}
        orders = extract_orders(msg)
        self.assertEqual(len(orders), 2)
        self.assertEqual([classify_order(o, PREF)['status'] for o in orders], ['rejected', 'needs_confirmation'])

    def test_distinct_media_never_merge_without_content_evidence(self):
        orders = []
        for mid in ('image1', 'image2'):
            extracted = extract_orders({'id': mid, 'group_name': '测试群', 'timestamp': 0, 'type': 3, 'content': ''})
            orders.extend(classify_order(o, PREF) for o in extracted)
        self.assertEqual(len(merge_orders(orders)), 2)

    def test_alternative_prices_never_reject_using_first_price(self):
        r = result('初一数学\n报酬：线上80元/小时，线下150元/小时')
        self.assertEqual(r['status'], 'needs_confirmation')
        self.assertIn('多种报价或计价方案待确认', r['reasons'])


if __name__ == '__main__':
    unittest.main()
