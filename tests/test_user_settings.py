import copy
import json
from pathlib import Path
import tempfile
import unittest

from src.user_settings import feedback_rows, normalize_feedback_value, load_user_settings, apply_user_settings, validate_overrides
from src.filter_rules import classify_order, extract_orders, profile_rejections, requirements_known
from src.report import render_raw
from tests.test_rules import PREF


def order(address='昌平区测试站附近', subject='数学', identifier='BJ999001'):
    raw = f'编号：{identifier}\n地址：{address}\n年级科目：二年级{subject}\n每周次数：一周1-2次\n每次时长：2h\n对老师的要求：男老师\n薪资：130/h'
    return extract_orders({'id': identifier, 'timestamp': 100, 'group_name': '测试群', 'type': 1, 'content': raw})[0]


class UserSettingsTests(unittest.TestCase):
    def test_structured_fields_but_no_prose_buttons(self):
        self.assertEqual(len(feedback_rows(order()['raw'])), 6)
        prose = 'A47474：北京市朝阳区世纪嘉园，初一，辅导理科，男女不限，大学生250-300/2h'
        self.assertEqual(feedback_rows(prose), [])
        self.assertNotIn('feedback-reject', render_raw({'raw': prose, 'status': 'needs_confirmation'}))
        self.assertIn('地址太远', render_raw({'raw': order()['raw'], 'status': 'needs_confirmation'}))

    def test_address_feedback_excludes_same_anchor_before_maps(self):
        preferences = copy.deepcopy(PREF)
        preferences['rejection_feedback'] = [{'order_key': 'BJold', 'field': 'address', 'value': '👑昌平区测试站附近', 'reason': '地址太远'}]
        matching = classify_order(order(), preferences)
        other = classify_order(order(address='昌平区另一个站附近'), preferences)
        self.assertEqual(matching['status'], 'rejected')
        self.assertIn('历史反馈排除：地址太远', matching['reasons'][0])
        self.assertFalse(any('历史反馈' in reason for reason in other['reasons']))
        self.assertEqual(normalize_feedback_value('address', '朝阳区立水桥南地铁站门口'),
                         normalize_feedback_value('address', '立水桥南站附近'))
        self.assertEqual(normalize_feedback_value('address', '北京站附近'), '北京站')
        prose = extract_orders({'id': 'prose', 'timestamp': 100, 'group_name': '测试群', 'type': 1,
                                'content': '昌平区测试站附近，二年级数学120元/小时'})[0]
        self.assertEqual(feedback_rows(prose['raw']), [])
        self.assertEqual(classify_order(prose, preferences)['status'], 'rejected')

    def test_other_fields_exact_match_not_broader_scope(self):
        preferences = copy.deepcopy(PREF)
        preferences['rejection_feedback'] = [{'order_key': 'BJold', 'field': 'subject', 'value': '二年级数学', 'reason': '科目不合适'}]
        self.assertEqual(classify_order(order(), preferences)['status'], 'rejected')
        self.assertNotEqual(classify_order(order(subject='英语'), preferences)['status'], 'rejected')
        self.assertNotEqual(normalize_feedback_value('frequency', '1-2次'), normalize_feedback_value('frequency', '12次'))
        self.assertNotEqual(normalize_feedback_value('teacher', '需要C#'), normalize_feedback_value('teacher', '需要C'))

    def test_two_label_structured_record_has_feedback(self):
        self.assertEqual(len(feedback_rows('地址：测试站附近\n薪资：130/h')), 2)
        numeric = '1、测试站附近\n2、二年级男孩\n3、数学\n4、一周一次\n5、男老师\n6、130/h'
        self.assertEqual(len(feedback_rows(numeric)), 6)

    def test_editable_profile_gender_stages_and_unknown_tiers(self):
        self.assertTrue(profile_rejections('男老师', {'gender': 'female'}))
        self.assertFalse(profile_rejections('男女不限', {'gender': 'female'}))
        self.assertTrue(profile_rejections('研一', {'academic_stage': 'master_2'}))
        self.assertFalse(profile_rejections('研二', {'academic_stage': 'master_2'}))
        self.assertTrue(profile_rejections('大三', {'academic_stage': 'undergraduate_2'}))
        self.assertFalse(profile_rejections('大二', {'academic_stage': 'undergraduate_2'}))
        settings = {'closed_order_keys': [], 'rejection_feedback': [], 'preference_overrides': {'tutor_profile.university_tiers.211': None}}
        base = copy.deepcopy(PREF)
        base['tutor_profile'] = {'university_tiers': {'211': True}}
        updated = apply_user_settings(base, settings)
        self.assertIsNone(updated['tutor_profile']['university_tiers']['211'])
        self.assertFalse(requirements_known('211大学生', updated['tutor_profile'], 3))

    def test_saved_file_applies_preferences_and_preserves_closed_reason(self):
        settings = {'closed_order_keys': ['BJ999001'], 'rejection_feedback': [
            {'order_key': 'BJ999001', 'field': 'pay', 'value': '130/h', 'reason': '薪资不合适'}],
            'preference_overrides': {'pay.minimum_hourly_cny': 150}}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'manual_closed_orders.json'
            path.write_text(json.dumps(settings), encoding='utf-8')
            preferences = apply_user_settings(PREF, load_user_settings(path))
            result = classify_order(order(), preferences)
            self.assertEqual(preferences['pay']['minimum_hourly_cny'], 150)
            self.assertEqual(result['status'], 'closed')
        self.assertEqual(result['reasons'], ['薪资不合适'])

    def test_chinese_order_identifier_can_be_saved(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'settings.json'
            path.write_text(json.dumps({'closed_order_keys': ['北101102'], 'rejection_feedback': [
                {'order_key': '北101102', 'field': 'pay', 'value': '130/h', 'reason': '薪资不合适'}]}), encoding='utf-8')
            self.assertEqual(load_user_settings(path)['closed_order_keys'], ['北101102'])

    def test_unknown_setting_and_bad_value_are_rejected(self):
        for overrides in ({'allow_private_chats': True}, {'pay.minimum_hourly_cny': -1},
                          {'pending_female_keyword_rejection': 'false'}, {'grades.accepted': ['未定义年级']}):
            with self.subTest(overrides=overrides), self.assertRaises(RuntimeError):
                validate_overrides(overrides)

    def test_edited_grade_range_is_used(self):
        settings = {'closed_order_keys': [], 'rejection_feedback': [], 'preference_overrides': {'grades.accepted': ['小学三年级']}}
        preferences = apply_user_settings(PREF, settings)
        self.assertEqual(classify_order(order(), preferences)['status'], 'rejected')
