import copy
import unittest

from src.filter_rules import time_result, classify_order, extract_orders, interval_result
from src.user_settings import validate_overrides
from tests.test_rules import PREF


class IntervalSettingsTests(unittest.TestCase):
    def test_known_duration_and_shorthand_end_cannot_bypass_intervals(self):
        self.assertEqual(interval_result('周一', [['09:00', '09:30']], 2, True), 'conflict')
        self.assertEqual(interval_result('周一18:00-20', [['18:00', '19:00']], 0.5), 'conflict')
    def test_multiple_intervals_cover_whole_session(self):
        pref = copy.deepcopy(PREF)
        pref['availability']['daily_intervals'] = {'1': [['09:00', '12:00'], ['18:00', '22:00']], '2': []}
        for schedule, expected in [('周一09:00-11:00', 'ok'), ('周一18:00-20:00', 'ok'),
                                   ('周一11:00-13:00', 'conflict'), ('周一13:00-15:00', 'conflict'),
                                   ('周一21:00-23:00', 'conflict'), ('周二18:00-19:00', 'conflict'),
                                   ('周一21:00，每次2小时', 'conflict')]:
            with self.subTest(schedule=schedule):
                self.assertEqual(time_result('时间：' + schedule, pref), expected)

    def test_validate_intervals_and_resume(self):
        validate_overrides({'availability.daily_intervals': {'1': [['18:00', '24:00']], '2': []},
                            'tutor_profile.resume': '大学生简历\n姓名：示例'})
        for intervals in [[['22:00', '18:00']], [['18:00', '20:00'], ['19:00', '21:00']], [['24:00', '24:00']]]:
            with self.assertRaises(RuntimeError):
                validate_overrides({'availability.daily_intervals': {'1': intervals}})

    def test_gender_keyword_mechanism_uses_profile_even_if_old_switch_off(self):
        for gender, opposite, same in [('male', '女', '男'), ('female', '男', '女')]:
            pref = copy.deepcopy(PREF)
            pref['tutor_profile'] = {'gender': gender}
            pref['pending_female_keyword_rejection'] = False
            raw = '年级：小学五年级\n科目：数学\n时间：待定\n报价：150元/小时\n地址：待定\n备注：' + opposite
            order = extract_orders({'id':'fixture','timestamp':100,'type':1,'group_name':'匿名群','content':raw})[0]
            result = classify_order(order, pref)
            self.assertEqual(result['status'], 'rejected')
            self.assertTrue(any(opposite in reason and same in reason for reason in result['reasons']))
