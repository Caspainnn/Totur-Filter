import copy
import unittest
from src.user_settings import validate_overrides, apply_user_settings
from src.filter_rules import classify_order, extract_orders, parse_grade, time_result
from tests.test_rules import PREF


class ExpandedSettingsTests(unittest.TestCase):
    def classify(self, grade, subject, overrides):
        settings = {'closed_order_keys': [], 'rejection_feedback': [], 'preference_overrides': overrides}
        preferences = apply_user_settings(copy.deepcopy(PREF), settings)
        raw = f'年级：{grade}\n科目：{subject}\n报价：200元/小时\n时间：周六14:00\n地址：线上\n教师要求：不限'
        order = extract_orders({'id': 'fixture', 'timestamp': 100, 'type': 1, 'group_name': '匿名群', 'content': raw})[0]
        return classify_order(order, preferences)

    def test_all_junior_subjects_and_grades_are_effective(self):
        overrides = {'grades.accepted': ['初中一年级', '初中二年级', '初中三年级'],
                     'subjects.by_stage': {'junior': {'mode': 'any', 'accepted': []}}}
        for subject in ['历史', '语文英语', '全科']:
            result = self.classify('初三', subject, overrides)
            self.assertFalse(any('科目' in reason or '全科' in reason or '年级超出' in reason for reason in result['reasons']))

    def test_custom_subject_requires_all_components(self):
        overrides = {'subjects.by_stage': {'primary': {'mode': 'custom', 'accepted': ['数学']}}}
        result = self.classify('五年级', '数学英语', overrides)
        self.assertEqual(result['status'], 'rejected')

    def test_legacy_primary_academic_list_does_not_accept_music_mix(self):
        self.assertEqual(self.classify('五年级', '数学钢琴', {})['status'], 'rejected')

    def test_custom_compound_subject_is_not_double_counted(self):
        result = self.classify('成人', '高等数学', {'grades.accepted':['成人'],
            'subjects.by_stage':{'adult':{'mode':'custom','accepted':['高等数学']}}})
        self.assertEqual(result['fields']['subjects'], ['高等数学'])
        self.assertNotEqual(result['status'], 'rejected')

    def test_preschool_senior_and_adult_grade_choices(self):
        self.assertEqual(parse_grade('年级：幼儿园中班')[0], -2)
        self.assertEqual(parse_grade('年级：成人')[0], 14)
        overrides = {'grades.accepted': ['幼儿园中班', '高中二年级', '成人'],
                     'subjects.by_stage': {stage: {'mode': 'any', 'accepted': []} for stage in ['preschool', 'senior', 'adult']}}
        for grade, subject in [('幼儿园中班', '识字'), ('高二', '数学'), ('成人', '英语')]:
            result = self.classify(grade, subject, overrides)
            self.assertNotEqual(result['status'], 'rejected')

    def test_stage_policy_and_location_validation(self):
        validate_overrides({'commute.city': '示例城市', 'commute.origin': '示例地铁站',
                            'subjects.by_stage': {'junior': {'mode': 'custom', 'accepted': ['历史']}}})
        for overrides in [{'subjects.by_stage': {'unknown': {'mode': 'any', 'accepted': []}}},
                          {'commute.origin': 'https://secret.example'},
                          {'subjects.by_stage': {'junior': {'mode': 'custom', 'accepted': []}}}]:
            with self.assertRaises(RuntimeError): validate_overrides(overrides)

    def test_unknown_subject_and_generic_grade_do_not_silently_pass(self):
        result = self.classify('五年级', '数学葡萄牙语', {'subjects.by_stage': {'primary': {'mode': 'custom', 'accepted': ['数学']}}})
        self.assertTrue(any('未识别科目' in reason for reason in result['reasons']))
        result = self.classify('小学', '数学', {'grades.accepted': ['初中一年级']})
        self.assertEqual(result['status'], 'rejected')
        self.assertEqual(parse_grade('年级：幼儿园中班和高二'), (None, True))

    def test_each_weekday_has_its_own_start(self):
        preferences = apply_user_settings(PREF, {'closed_order_keys': [], 'rejection_feedback': [],
            'preference_overrides': {'availability.daily_start': {'1':'18:00', '2':'16:00', '3':'off'}}})
        self.assertEqual(time_result('时间：周一17:00', preferences), 'conflict')
        self.assertEqual(time_result('时间：周二17:00', preferences), 'ok')
        self.assertEqual(time_result('时间：周三19:00', preferences), 'conflict')
        self.assertEqual(time_result('时间：周三', preferences), 'conflict')
