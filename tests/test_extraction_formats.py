import json
from pathlib import Path
import unittest
from src.filter_rules import extract_orders, classify_order

PREF = json.loads((Path(__file__).resolve().parents[1] / 'tests/fixtures/preferences.json').read_text(encoding='utf-8'))
PREF['tutor_profile'] = {'gender': 'male', 'academic_stage': 'master_1', 'university': '示例理工大学', 'university_aliases': ['示例理工大学', '示工']}
PREF['tutor_profile']['university_tiers'] = {'211': True, '985': False}
PREF['pending_female_keyword_rejection'] = False  # Test field extraction independently of keyword policy.


def message(raw):
    return {'id': 'fixture', 'group_name': '测试群', 'timestamp': 100000, 'type': 1, 'content': raw}


def classify(raw):
    return [classify_order(o, PREF) for o in extract_orders(message(raw))]


class FormatTests(unittest.TestCase):
    def test_combined_senior_stage_with_separate_subject_teachers(self):
        result=classify('＃海淀机构单\n北京线下gy99000001\n【年级科目】高中，数学物理（各一位）\n【辅导地点】海淀测试站附近\n【课时报酬】400/2h\n【时间次数】一周2次课，一次课2小时，周末\n【学生情况】虚构样例，一对一\n【老师要求】男女不限，有教学经验')[0]
        self.assertEqual(result['fields']['grade'],'senior')
        self.assertEqual(set(result['fields']['subjects']),{'数学','物理'})
        self.assertTrue(result['fields']['separate_subject_teachers'])
        self.assertEqual(result['fields']['hourly_cny'],[200,200])
        self.assertIn('测试站',result['fields']['address'])
    def test_agency_inline_fields_shared_grades_and_daily_morning(self):
        raw='DGBJ990000001#机构月结 【年级】5.6年级 【辅导科目】语数英 【上课区域】朝阳区示例(北京)教学园区A1 【上课时段】每天早8-9:30 【预算范围】250/h 【老师性别】男女不限 【备注】虚构示例#有经验'
        result=classify(raw)[0]
        self.assertEqual(result['fields']['address'],'朝阳区示例(北京)教学园区A1')
        self.assertEqual(result['fields']['schedule'],'每天早8-9:30')
        self.assertEqual(result['fields']['grade_candidates'],[5,6])
        self.assertIsNone(result['fields']['grade'])
        self.assertEqual(set(result['fields']['subjects']),{'语文','数学','英语'})
        self.assertEqual(result['fields']['hourly_cny'],[250,250])
    def test_short_hash_ids_split_fields_without_blank_lines(self):
        raw = 'sender:\nX9901#朝阳区测试地点\n年级：一年级\n科目：英语\n报酬：每小时100-150\nX9902#海淀区测试地点\n年级：高一\n科目：数学物理\n报酬：每小时150-200\nX9903#朝阳区测试地点\n年级：2岁\n科目：英语\n报酬：每小时90'
        orders = classify(raw)
        self.assertEqual(len(orders), 3)
        self.assertEqual([o['fields']['grade'] for o in orders], [1, 10, None])
        self.assertEqual([o['fields']['hourly_cny'] for o in orders], [[100, 150], [150, 200], [90, 90]])
        self.assertEqual([o['fields']['address'] for o in orders], ['朝阳区测试地点', '海淀区测试地点', '朝阳区测试地点'])
        self.assertNotIn('X9902', orders[0]['raw'])

    def test_blank_lines_split_complete_orders_but_not_one_orders_layout(self):
        first = '年级：一年级\n科目：数学\n报酬：120/h'
        second = '年级：四年级\n科目：英语\n报酬：150/h'
        orders = classify(first + '\n\n' + second)
        self.assertEqual(len(orders), 2)
        self.assertEqual([o['fields']['grade'] for o in orders], [1, 4])
        self.assertEqual(len(extract_orders(message('年级：一年级\n\n科目：数学\n\n报酬：120/h'))), 1)
    def test_emoji_numeric_batch_headers_and_hourly_labels(self):
        blocks = []
        for index in range(1, 7):
            blocks.append(f'💜9900990{index}\n【上门地址】：海淀区测试{index}小区\n【年级科目】：二年级数学英语\n【次数时间】：一周{index}次 一次2h\n【老师时薪】：' + ('100h' if index == 2 else '100-130/h') + '\n【要求】：男女不限')
        orders = classify('sender:\n' + '\n'.join(blocks))
        self.assertEqual(len(orders), 6)
        for index, order in enumerate(orders, 1):
            self.assertEqual(order['fields']['schedule'], f'一周{index}次 一次2h')
            self.assertEqual(order['fields']['hourly_cny'], [100, 100] if index == 2 else [100, 130])
            self.assertNotIn('💜', order['fields']['teacher_requirements'])
            self.assertEqual(order['raw'].count('💜'), 1)
    def test_numeric_district_and_xa_headers_split(self):
        for first, second in [('9901（北京东城区）', '9902（北京海淀区）'), ('XA99000000001', 'XA99000000002')]:
            raw = first + '\n「年级」：初三\n「科目」：数学\n「课时费」：200/2h\n' + second + '\n「年级」：四年级\n「科目」：数学\n「课时费」：240/2h'
            orders = classify(raw)
            self.assertEqual(len(orders), 2)
            self.assertEqual([order['fields']['grade'] for order in orders], [9, 4])
            self.assertEqual([order['fields']['hourly_cny'] for order in orders], [[100, 100], [120, 120]])

    def test_repeated_student_subject_labels_split(self):
        orders = classify('学员科目：四年级英语\n报酬：120/h\n学员科目：初一数学\n报酬：150/h')
        self.assertEqual(len(orders), 2)
        self.assertEqual([order['fields']['grade'] for order in orders], [4, 7])
    def test_tutor_compilation_ids_split_with_sender_and_inline_headers(self):
        raw = 'sender: 家教编单：990099001\n地址：海淀区测试小区\n学生情况：初二 女孩 数学\n时间次数：协商\n老师要求：男女不限\n时薪：110-130/h\n家教编单：990099002\n地址：昌平区测试小区\n学生情况：四年级 男孩 教孩子唱歌\n时间次数：周日上午一次 一次2小时\n老师要求：男女不限\n时薪：100-120/h'
        orders = classify(raw)
        self.assertEqual(len(orders), 2)
        self.assertEqual([order['fields']['grade'] for order in orders], [8, 4])
        self.assertEqual([order['fields']['hourly_cny'] for order in orders], [[110, 130], [100, 120]])
        self.assertIn('年级不在用户选择的范围内', orders[0]['reasons'])
        self.assertEqual(orders[1]['fields']['subjects'], ['声乐'])
        self.assertEqual(orders[1]['status'], 'rejected')
        self.assertNotIn('990099002', orders[0]['raw'])
    def test_beijing_offline_headers_keep_prices_separate(self):
        orders = classify('北京线下99000001D\n【年级】：一年级\n【科目】：英语\n【课费】：100-120/h\n北京线下99000002D\n【年级】：高一\n【科目】：语文\n【课费】：150-160/h')
        self.assertEqual(len(orders), 2)
        self.assertEqual(orders[0]['fields']['hourly_cny'], [100, 120])
        self.assertEqual(orders[1]['fields']['hourly_cny'], [150, 160])

    def test_conditional_professional_pay_does_not_override_regular_pay(self):
        order = classify('年级科目：一年级英语\n课费：110-130/h，如有专职老师愿意可以200-240/h')[0]
        self.assertEqual(order['fields']['hourly_cny'], [110, 130])
        self.assertNotIn('多种报价或计价方案待确认', order['reasons'])
    def test_address_decoration_and_prose_cleaned(self):
        cases = {'🍑#北京市西城区广安门外': '北京市西城区广安门外',
                 '#北京市在团结湖这里': '北京市团结湖', '👑线上': '线上'}
        for original, expected in cases.items():
            with self.subTest(address=original):
                order = classify('初一数学120元/小时\n地址：' + original)[0]
                self.assertEqual(order['fields']['address'], expected)
    def test_bare_identifier_and_recycling_notices_are_ignored(self):
        for raw in ('【编号】回收DX9901', '编号：DX9901', '【编号】取消DX9901'):
            with self.subTest(raw=raw):
                self.assertEqual(extract_orders(message(raw)), [])
        self.assertEqual(len(extract_orders(message('【编号】DX9901\n初一数学120元/小时'))), 1)
    def test_observed_label_aliases_and_teacher_boundaries(self):
        for address_label in ('补习地址', '上门地址', '辅导位置', '学员地址', '住址', '坐标'):
            with self.subTest(label=address_label):
                raw = f'【补习年级科目】：小学三年级数学\n【补习科目】：数学\n【对老师要求】：男老师\n【{address_label}】：海淀区测试小区\n【补习时间】：周三18:00\n【课时薪水】：120/h'
                order = classify(raw)[0]
                self.assertEqual(order['fields']['address'], '海淀区测试小区')
                self.assertEqual(order['fields']['grade'], 3)
                self.assertEqual(order['fields']['subjects'], ['数学'])
                self.assertEqual(order['fields']['hourly_cny'], [120, 120])
                self.assertNotIn('海淀', order['fields']['teacher_requirements'])

    def test_student_school_address_is_not_tutoring_address(self):
        order = classify('初一数学120元/小时\n孩子学校地址：海淀区测试学校')[0]
        self.assertEqual(order['fields']['address'], '')
    def test_decorated_order_ids_are_separate_raw_cards(self):
        raw = '编号：👑BJ990001\n年级科目：一年级数学\n薪酬：120/h\n编号：[Waddle]BJ990002[Twirl]\n年级科目：初一英语\n薪酬：150/h\n编号：👑BJ990003\n年级科目：五年级数学\n薪酬：130/h'
        orders = extract_orders(message(raw))
        self.assertEqual(len(orders), 3)
        for index, order in enumerate(orders, 1):
            self.assertIn('BJ99000' + str(index), order['raw'])
            for other in range(1, 4):
                if other != index:
                    self.assertNotIn('BJ99000' + str(other), order['raw'])
    def test_bracketed_tutoring_address_preserves_station(self):
        orders = classify('初一数学120元/小时\n【辅导地址】:海淀区测试桥地铁站附近')
        self.assertEqual(orders[0]['fields']['address'], '海淀区测试桥地铁站附近')
    def test_number_headers_split_without_cross_order_fields(self):
        raw = '编号：BJW990001\n地址：海淀区测试小区\n年级科目：初一数学\n对老师的要求：男老师\n薪酬：120/h\n========\n编号：BJW990002\n地址：通州区测试小区\n年级科目：初二物理\n对老师的要求：女老师\n薪酬：90元/3小时/次课'
        orders = classify(raw)
        self.assertEqual(len(orders), 2)
        self.assertEqual(orders[0]['fields']['grade'], 7)
        self.assertEqual(orders[0]['fields']['hourly_cny'], [120, 120])
        self.assertEqual(orders[1]['status'], 'rejected')
        self.assertEqual(orders[1]['fields']['hourly_cny'], [30, 30])
        self.assertNotIn('女老师', orders[0]['fields']['teacher_requirements'])

    def test_plain_bj_and_beijing_headers_split(self):
        raw = 'bj99901\n二年级英语启蒙 100-120/h\n\nbj99902\n初二数学 200/h\n\n北京C990003 四年级数学，在校女大学生100每小时，地址：昌平区测试小区'
        orders = classify(raw)
        self.assertEqual(len(orders), 3)
        self.assertNotEqual(orders[0]['status'], 'rejected')
        self.assertTrue(all(o['status'] == 'rejected' for o in orders[1:]))

    def test_six_row_template_role_gender_and_district(self):
        raw = '北京BY990001\n1、大兴区测试小区\n2、7年级，男\n3、数学\n4、一周2次，一次2h，周三晚上\n5、女，研究生\n6、130-150/h'
        order = classify(raw)[0]
        self.assertEqual(order['fields']['grade'], 7)
        self.assertEqual(order['fields']['address'], '大兴区测试小区')
        self.assertEqual(order['fields']['hourly_cny'], [130, 150])
        self.assertIn('教师性别要求不符：仅招女性', order['reasons'])
        self.assertIn('授课地点在黑名单：大兴区', order['reasons'])

    def test_bracket_fields_and_unsupported_course(self):
        raw = '【年级科目】小学生（西班牙语发音）\n【辅导地点】测试街\n【课费报酬】350/次（一次1.5小时）\n【时间次数】周三下午\n【老师要求】大学生有经验'
        order = classify(raw)[0]
        self.assertEqual(order['status'], 'rejected')
        self.assertAlmostEqual(order['fields']['hourly_cny'][0], 350 / 1.5)
        self.assertEqual(order['fields']['address'], '测试街')
        self.assertNotIn('】', order['fields']['schedule'])

    def test_unlabelled_explicit_female_teacher_and_blocked_address(self):
        first = classify('A99901：北京市西城区测试小区，初一数学，孩子是女生，两周一次，周末为主，大学生240-300/2h，只要女老师，数学系优先')[0]
        self.assertEqual(first['fields']['hourly_cny'], [120, 150])
        self.assertEqual(first['status'], 'rejected')
        self.assertIn('教师性别要求不符：仅招女性', first['reasons'])
        second = classify('北京B990001 初一数学，孩子女生，男大学生120每小时，周末上课，地址：大兴区测试小区')[0]
        self.assertIn('授课地点在黑名单：大兴区', second['reasons'])

    def test_all_subjects_junior_not_primary_all_subjects(self):
        self.assertEqual(classify('年级科目：初一全科\n报酬：120/h')[0]['status'], 'rejected')

    def test_shadow_teacher_clear_schedule_and_pay(self):
        raw = '编号：BJ990001\n年级科目：6岁影子老师\n每周次数：5次，周一到周五，上午8点到12点\n每次时长：4h\n对老师的要求：大学生\n薪酬：200/次'
        order = classify(raw)[0]
        self.assertEqual(order['status'], 'rejected')
        self.assertEqual(order['fields']['hourly_cny'], [50, 50])
        self.assertIn('上课时间冲突', order['reasons'])

    def test_ket_and_vocal_recognized_as_outside_subjects(self):
        for subject in ('声乐', '蒙古语'):
            self.assertEqual(classify(f'年级科目：小学三年级{subject}\n课费：200/2h')[0]['status'], 'rejected')
        for subject in ('剑桥KET', '中文'):
            self.assertNotEqual(classify(f'年级科目：小学三年级{subject}\n课费：200/2h')[0]['status'], 'rejected')

    def test_missing_colon_headers_still_isolate_orders(self):
        orders = classify('编号BJ990001\n年级科目：初一数学\n薪酬：120/h\n要求：男老师\n编号BJ990002\n年级科目：初二英语\n薪酬：90元/3小时\n要求：女老师')
        self.assertEqual(len(orders), 2)
        self.assertNotEqual(orders[0]['status'], 'rejected')

    def test_teacher_field_stops_before_combined_student_and_pay_labels(self):
        order = classify('【老师要求】不限\n【年级科目】初一数学，女生\n【薪酬】120/h\n【时间】周末')[0]
        self.assertEqual(order['status'], 'rejected')
        self.assertTrue(any('待确认原文' in reason for reason in order['reasons']))
        self.assertNotIn('女生', order['fields']['teacher_requirements'])

    def test_current_price_not_overridden_by_historical_note(self):
        order = classify('年级科目：初一数学\n薪酬：120/h\n备注：之前老师收费90元/3小时\n时间：周末')[0]
        self.assertEqual(order['fields']['hourly_cny'], [120, 120])
        self.assertNotEqual(order['status'], 'rejected')
        alternative = classify('年级科目：初一数学\n薪酬：90元/3小时\n报酬：可改为120/h')[0]
        self.assertEqual(alternative['status'], 'needs_confirmation')

    def test_female_full_time_and_unlabelled_blocked_location(self):
        self.assertEqual(classify('三年级数学\n老师要求：女专职在职\n老师报酬200每小时')[0]['status'], 'rejected')
        order = classify('三年级数学，一周两次，每次1小时，顺义区测试小区，100-150/h')[0]
        self.assertIn('授课地点在黑名单：顺义区', order['reasons'])

    def test_unallowed_sports_programming_and_exam_course(self):
        for raw in ('三年级，会打网球的，教打网球，100/h', '三年级，会拉小提琴的，理科生，100/h', '年级：三年级\n科目：计算机C++\n课时费：120/h', '学生学习情况：备考FCE\n课时费：老师报价\n要求：会讲FCE语用'):
            self.assertEqual(classify(raw)[0]['status'], 'rejected')

    def test_english_math_not_two_subjects_and_student_pay_branch(self):
        raw = '年级：六年级\n科目：数学 英文体系的数学 教Aops\n课时费：大学生每小时100到150 专职老师每小时200到300\n要求：大学生：985 数学专业 有经验 专职老师：教Aops经验丰富'
        order = classify(raw)[0]
        self.assertEqual(order['fields']['subjects'], ['数学'])
        self.assertEqual(order['fields']['hourly_cny'], [100, 150])
        self.assertIn('985', order['fields']['teacher_requirements'])
        self.assertEqual(order['status'], 'rejected')

    def test_211_or_985_not_same_as_985_only(self):
        self.assertNotEqual(classify('初一数学120/h\n老师要求：985/211大学生')[0]['status'], 'rejected')
        self.assertEqual(classify('初一数学120/h\n老师要求：只要985大学生')[0]['status'], 'rejected')

    def test_repeated_address_blocks_without_second_id_are_separate_orders(self):
        raw = '北京990001\n联系地址：东城区测试小区\n年级性别：二年级\n辅导科目：全科\n老师报酬：90一小时\n老师要求：大学生\n\n联系地址：丰台区测试小区\n年级性别：高一\n辅导科目：物理\n老师报酬150一小时\n老师要求大学生'
        orders = classify(raw)
        self.assertEqual(len(orders), 2)
        self.assertEqual([o['fields']['hourly_cny'][0] for o in orders], [90, 150])
        self.assertTrue(all(o['status'] == 'rejected' for o in orders))


if __name__ == '__main__':
    unittest.main()
