import unittest

from src.filter_rules import extract_orders, classify_order, order_identifier
from src.report import render_key_information
from src.user_settings import feedback_rows
from tests.test_rules import PREF


FIRST = '''北京BY26101604#加急（优质家长）昌平的优质家长
1、昌平-天通苑
2、7岁，男孩
3、陪玩+陪学（陪玩占比高），孩子的兴趣（三角洲、做手工、滑板等）
4、一周一次，周五下午5-8点（稍微延迟一点点，家长不希望按时到按时走），一次3h，#最好可以今天上课
5、92，男大，英语专业的最好，性格外向能玩游戏，情商高，能想象游戏玩更好，性格要好，人品三观正
6、90-110/h'''
SECOND = '''上海BY26101705
1、红莲南路地铁站A口
2、高一，女孩
3、最好能数学英语物理都能辅导，数学目前处于及格边缘上下徘徊，基础薄弱，需要有教学经验有方法会引导思考的老师帮助打好基础，目前主攻基础和中档题，期中的预期希望能达到80分左右；英语带着背单词和做阅读理解完形这一块；物理也是主抓校内基础和中档题
4、每周2-3次课，一次2h，周内晚+周末#老师提供符合时间段
5、985在读+女生
6、150/h'''


def message(raw):
    return {'id': 'numeric', 'timestamp': 100000, 'group_name': '测试群', 'type': 1, 'content': raw}


class NumericBatchTests(unittest.TestCase):
    def test_mixed_city_numeric_templates_are_two_orders(self):
        for separator in ['\n', '\n\n', '\n———————————————\n']:
            orders = extract_orders(message(FIRST + separator + SECOND))
            self.assertEqual(len(orders), 2)
            self.assertEqual([order_identifier(o['raw']) for o in orders], ['北京BY26101604', '上海BY26101705'])
            first, second = [classify_order(o, PREF) for o in orders]
            self.assertIn('天通苑', first['fields']['address'])
            self.assertEqual(first['fields']['hourly_cny'], [90, 110])
            self.assertIsNone(first['fields']['grade'])  # Age does not establish a school grade.
            self.assertEqual(second['fields']['grade'], 10)
            self.assertEqual(second['fields']['hourly_cny'], [150, 150])
            self.assertNotIn('红莲南路', first['raw'])
            self.assertNotIn('陪玩', second['raw'])

    def test_repeated_numeric_templates_without_headers(self):
        raw = FIRST.split('\n', 1)[1] + '\n' + SECOND.split('\n', 1)[1]
        orders = extract_orders(message(raw))
        self.assertEqual(len(orders), 2)
        result = [classify_order(o, PREF) for o in orders]
        self.assertIn('天通苑', result[0]['fields']['address'])
        self.assertIn('红莲南路', result[1]['fields']['address'])
        self.assertEqual(result[1]['fields']['hourly_cny'], [150, 150])

    def test_unsplit_numeric_batch_is_parse_failure_without_feedback(self):
        raw = FIRST + '\n' + SECOND
        result = classify_order({'raw': raw, 'type': 1, 'sources': [message(raw)]}, PREF)
        self.assertEqual(result['status'], 'parse_failed')
        self.assertEqual(result['fields'], {})
        self.assertEqual(feedback_rows(raw), [])
        self.assertNotIn('feedback-reject', render_key_information(result, '', ''))
