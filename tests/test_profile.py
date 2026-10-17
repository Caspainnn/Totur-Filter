import copy
import json
from pathlib import Path
import unittest
from src.filter_rules import extract_orders, classify_order, requirements_known
from src.commute import enrich_order

PREF = json.loads((Path(__file__).resolve().parents[1] / 'tests/fixtures/preferences.json').read_text(encoding='utf-8'))
PREF['tutor_profile'] = {'gender': 'male', 'academic_stage': 'master_1', 'university': '示例理工大学', 'university_aliases': ['示例理工大学', '示工', 'EXAMPLE']}
PREF['pending_female_keyword_rejection'] = False
PREF['location_blacklist'] = ['门头沟区', '房山区', '通州区', '顺义区', '大兴区', '延庆区', '怀柔区', '密云区', '平谷区']


def screened(requirement='', address='昌平区测试小区', extra=''):
    text = f'初一数学 120元/小时\n地址：{address}\n时间：周三18:00\n老师要求：{requirement}\n{extra}'
    message = {'id': 'fixture', 'group_name': '测试群', 'timestamp': 100000, 'type': 1, 'content': text}
    return classify_order(extract_orders(message)[0], PREF)


class ProfileTests(unittest.TestCase):
    def test_confirmed_experience_is_scoped_and_does_not_infer_specialties(self):
        profile = copy.deepcopy(PREF['tutor_profile'])
        profile['teaching_experience_levels'] = ['primary', 'junior']
        for grade in (1, 6, 7, 9):
            self.assertTrue(requirements_known('男女不限，有经验', profile, grade))
            self.assertTrue(requirements_known('最好男老师，有经验', profile, grade))
        self.assertFalse(requirements_known('男女不限，有经验', profile, 10))
        self.assertFalse(requirements_known('男女不限，有经验', profile, None))
        self.assertFalse(requirements_known('经验丰富，有中考辅导经验', profile, 7))
    def test_pending_female_keyword_rule(self):
        preferences = copy.deepcopy(PREF)
        preferences['pending_female_keyword_rejection'] = True
        for extra, expected in [('学生性别：女', 'rejected'),
                                ('学生性别：女，另有男学生', 'needs_confirmation'),
                                ('学生性别：男', 'needs_confirmation')]:
            message = {'id': 'keyword', 'group_name': '测试群', 'timestamp': 100000,
                       'type': 1, 'content': '初一数学120元/小时\n地址：昌平区测试小区\n' + extra}
            result = classify_order(extract_orders(message)[0], preferences)
            self.assertEqual(result['status'], expected)

    def test_female_teacher_requirements_rejected(self):
        for requirement in ('女老师', '限女生，研究生', '性别女', '女性，大学生'):
            with self.subTest(requirement=requirement):
                result = screened(requirement)
                self.assertEqual(result['status'], 'rejected')
                self.assertIn('教师性别要求不符：仅招女性', result['reasons'])

    def test_gender_keyword_rule_preserves_both_gender_cases(self):
        for requirement in ('男女不限', '男生女生都可', '不要女老师，男老师即可'):
            with self.subTest(requirement=requirement):
                self.assertNotEqual(screened(requirement)['status'], 'rejected')
        self.assertNotEqual(screened('男老师', extra='学生性别：女')['status'], 'rejected')
        for requirement in ('女老师优先', '不要求女老师'):
            self.assertEqual(screened(requirement)['status'], 'rejected')

    def test_incompatible_teacher_years_rejected(self):
        for requirement in ('大一大二', '本科大三', '只限本科生', '研二研三'):
            with self.subTest(requirement=requirement):
                self.assertEqual(screened(requirement)['status'], 'rejected')

    def test_degree_alternatives_and_lower_bound_allowed(self):
        for requirement in ('本科或研究生均可', '大一及以上', '研究生在读', '研一', '大一大二优先', '不要大一大二'):
            with self.subTest(requirement=requirement):
                self.assertNotEqual(screened(requirement)['status'], 'rejected')

    def test_other_school_restricted_rejected(self):
        for requirement in ('清华北大学生', '北京师范大学', '限北航', '中国传媒大学学生', '只要清北'):
            with self.subTest(requirement=requirement):
                self.assertEqual(screened(requirement)['status'], 'rejected')

    def test_own_school_alternatives_and_school_preference_allowed(self):
        for requirement in ('示工', '示例理工大学研一男生', '示工、北师大均可', '北大优先，其他学校也可', '学校不限'):
            with self.subTest(requirement=requirement):
                self.assertNotEqual(screened(requirement)['status'], 'rejected')
        self.assertEqual(screened('不要示工')['status'], 'rejected')

    def test_all_nine_districts_and_shorthand_rejected(self):
        for district in PREF['location_blacklist']:
            for address in (district + '测试小区', district.removesuffix('区') + '测试小区'):
                with self.subTest(address=address):
                    result = screened('', address)
                    self.assertEqual(result['status'], 'rejected')
                    self.assertIn('授课地点在黑名单：' + district, result['reasons'])

    def test_district_in_teacher_description_not_location(self):
        self.assertNotEqual(screened('有通州区授课经验')['status'], 'rejected')
        self.assertNotEqual(screened('', '海淀区密云路测试小区')['status'], 'rejected')

    def test_rejected_profile_never_calls_map(self):
        class MustNotCall:
            calls = 0
            def commute(self, *args):
                self.calls += 1
                raise AssertionError('Map must not run')
        order = screened('女老师')
        client = MustNotCall()
        self.assertEqual(enrich_order(order, PREF, client, 100000)['status'], 'rejected')
        self.assertEqual(client.calls, 0)

    def test_teacher_requirement_field_boundaries(self):
        self.assertNotEqual(screened('男老师 学生性别：女生')['status'], 'rejected')
        self.assertNotEqual(screened('男老师', extra='授课地址：海淀区北京大学附近')['status'], 'rejected')

    def test_soft_school_or_experience_cannot_hide_hard_requirement(self):
        self.assertEqual(screened('女老师 示工优先')['status'], 'rejected')
        self.assertEqual(screened('只要北航且有经验')['status'], 'rejected')

    def test_negation_respects_profile(self):
        self.assertNotEqual(screened('不考虑女老师，男生即可')['status'], 'rejected')
        self.assertNotEqual(screened('不要北大')['status'], 'rejected')
        self.assertEqual(screened('不要研一')['status'], 'rejected')

    def test_fully_known_matching_profile_not_left_unconfirmed(self):
        self.assertNotIn('教师要求需本人确认', screened('示例理工大学研一男生')['reasons'])

    def test_only_own_school_negation_and_exclusion(self):
        self.assertNotEqual(screened('非示工勿扰')['status'], 'rejected')
        self.assertNotEqual(screened('不要非示工')['status'], 'rejected')
        self.assertEqual(screened('示工勿扰')['status'], 'rejected')


if __name__ == '__main__':
    unittest.main()
