import unittest

from src.filter_rules import extract_orders, classify_order, order_identifier
from src.report import render_key_information, render_raw
from tests.test_rules import PREF


BLOCKS = [
    '北京线下25832\n地址：#工体\n辅导科目：理科陪读\n学员情况：高一女\n教员要求：女大，有经验，985理科生#北京生源\n时间安排：周末3-4小时\n课时费:160/h',
    '北京线下25756\n地址：#海淀区凤仪佳苑一里\n辅导科目：英语\n学员情况：五年级#一男一女\n教员要求：大学生，有经验，英语好，有考级\n时间安排：一周一次周日2-3h\n课时费:150/h',
    '北京线下26784\n地址：#朝阳去长楹天街附近\n辅导科目：全科辅导\n学员情况：初一男\n教员要求：大学生有经验，作业辅导培养习惯，给孩子做计划\n时间安排：一周2-3次一次两小时\n课时费：120/h 240一次课',
    '北京线下26785\n地址：#朝阳官庄（近北科大）\n辅导科目：ket/pet\n学员情况：六年级男#ket考了没过\n教员要求：大学生剑桥体系有经验，六年级结束前考完pet\n时间安排：周末一次两小时，周中可能会线上\n课时费：120-150/h 240-300一次课',
    '北京线下26786\n地址：#朝阳新城市广场附近\n辅导科目：英语\n学员情况：一年级男#零基础\n教员要求：需要找有经验的大学生或者研究生，需要看学生证，英语专业女生\n时间安排：每周1-2次，下午4:30~6:00或者5:00~6:30\n课时费：120/h 180一次课',
]


def extract(raw):
    return extract_orders({'id': 'batch', 'timestamp': 100000, 'group_name': '测试群', 'type': 1, 'content': raw})


class BatchBoundaryTests(unittest.TestCase):
    def test_five_digit_headers_split_with_or_without_blank_lines(self):
        for separator in ['\n', '\n\n', '\r\n \r\n']:
            orders = extract('sender:\n' + separator.join(BLOCKS))
            self.assertEqual(len(orders), 5)
            self.assertEqual([order_identifier(o['raw']) for o in orders],
                             ['北京线下25832', '北京线下25756', '北京线下26784', '北京线下26785', '北京线下26786'])
            result = [classify_order(o, PREF) for o in orders]
            self.assertEqual([o['fields']['grade'] for o in result], [10, 5, 7, 6, 1])
            for index, order in enumerate(orders):
                self.assertIn(BLOCKS[index], order['raw'])
                self.assertEqual(order['raw'].count('课时费'), 1)

    def test_blank_blocks_with_student_labels_and_no_ids(self):
        blocks = [b.split('\n', 1)[1] for b in BLOCKS]
        self.assertEqual(len(extract('\n\n'.join(blocks))), 5)
        self.assertEqual(len(extract('年级：一年级\n\n科目：英语\n\n课时费：120/h')), 1)

    def test_unsplit_batch_fails_before_preference_rejections(self):
        order = extract(BLOCKS[0])[0]
        order['raw'] = '\n'.join(BLOCKS)
        result = classify_order(order, PREF)
        self.assertEqual(result['status'], 'parse_failed')
        self.assertEqual(result['fields'], {})
        self.assertIn('拆分', result['reasons'][0])
        self.assertNotIn('feedback-reject', render_key_information(result, '', ''))
        self.assertNotIn('feedback-reject', render_raw(result))
