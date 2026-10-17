import unittest
from src.report import confirmation_heading, candidate_priority, render_report
from html.parser import HTMLParser


class ConfirmationHeadingTests(unittest.TestCase):
    def test_unknown_grade_has_universal_dismiss_in_title(self):
        order={'status':'needs_confirmation','fingerprint':'unknown','raw':'示例','fields':{},'reasons':['年级待确认'],
               'sources':[{'group_name':'匿名群','timestamp':100000}]}
        html=render_report([order],{'generated_at':100000,'new_orders':0,'messages_read':0})
        self.assertIn('class="order-heading"',html)
        self.assertIn('data-feedback-field="order" data-feedback-value="unknown" data-feedback-reason="手动排除"',html)
        self.assertIn('class="feedback-reject dismiss-order"',html)
    def test_legacy_closed_orders_are_shown_in_rejected_only(self):
        order={'status':'closed','fingerprint':'taken','raw':'示例订单','fields':{},
               'reasons':['熄单：用户已确认被别人接走'],
               'sources':[{'group_name':'匿名群','timestamp':100000}]}
        html=render_report([order],{'generated_at':100000,'new_orders':0,'messages_read':0})
        self.assertNotIn('id="closed"',html)
        self.assertNotIn('data-category="closed"',html)
        self.assertIn('<p class="reason">单已被抢走</p>',html)
        section=html.split('id="rejected"')[1].split('</section>')[0]
        self.assertIn('data-order-key="taken"',section)
        self.assertNotIn('class="close-order"',section)
    def test_workspace_summary_is_escaped_and_keeps_key_information_open(self):
        order = {'status': 'needs_confirmation', 'fingerprint': 'fixture',
                 'raw': '科目：五年级数学\n时间：周六待确认',
                 'fields': {'grade': 5, 'subjects': ['数学'], 'address': '<测试地点>',
                            'hourly_cny': [100, 120], 'schedule': '周六待确认'},
                 'reasons': ['上课时间待确认'],
                 'sources': [{'group_name': '匿名群', 'timestamp': 100000}]}
        html = render_report([order], {'generated_at': 100000, 'new_orders': 1, 'messages_read': 1})
        class Tags(HTMLParser):
            def __init__(self): super().__init__(); self.items = []
            def handle_starttag(self, tag, attrs): self.items.append((tag, dict(attrs)))
        parser = Tags(); parser.feed(html)
        tags = parser.items
        card = next(attrs for tag, attrs in tags if tag == 'article')
        self.assertEqual(card['data-title'], '小学五年级 · 数学')
        self.assertEqual(card['data-address'], '<测试地点>')
        self.assertEqual(card['data-price'], '100–120元/小时')
        self.assertIn('id="order-list"', html)
        self.assertIn('id="sort-orders"', html)
        self.assertIn('<option value="time">时间倒序</option>', html)
        self.assertIn('data-category="preferences" href="#preferences">用户设置', html)
        self.assertIn('class="key-information" open', html)
        self.assertNotIn('<测试地点>', html)

    def test_preferred_address_breaks_ties_without_overriding_newness(self):
        def order(name, timestamp, address):
            return {'name': name, 'sources': [{'timestamp': timestamp}], 'fields': {'address': address}, 'reasons': []}
        orders = [order('other', 100, '海淀'), order('preferred', 100, '昌平沙河'), order('newest', 101, '海淀')]
        ranked = sorted(orders, key=lambda item: candidate_priority(item, ['昌平', '沙河']), reverse=True)
        self.assertEqual([item['name'] for item in ranked], ['newest', 'preferred', 'other'])
    def test_priority_newer_first_then_more_confirmed_with_stable_ties(self):
        def candidate(name, timestamp, subjects):
            return {'name': name, 'sources': [{'timestamp': timestamp}],
                    'fields': {'subjects': subjects}, 'reasons': []}
        older = candidate('older', 100, ['数学'])
        newer = candidate('newer', 101, [])
        fewer = candidate('fewer', 100, [])
        tied = candidate('tied', 100, ['数学'])
        ordered = sorted([fewer, older, tied, newer], key=candidate_priority, reverse=True)
        self.assertEqual([order['name'] for order in ordered], ['newer', 'older', 'tied', 'fewer'])
    def test_reference_commute_and_crossing_price_remain_pending(self):
        order = {'fields': {'subjects': ['数学'], 'schedule': '周三18:00',
                            'hourly_cny': [90, 100], 'commute': {'status': 'ok', 'verified_schedule': False}},
                 'reasons': ['报价范围跨越最低时薪', '上课时段未明确，通勤仅为参考估算']}
        heading = confirmation_heading(order)
        self.assertEqual(heading.count('aria-label="通过"'), 3)
        self.assertEqual(heading.count('aria-label="待确认"'), 2)

    def test_unknown_fields_are_not_shown_as_passed(self):
        order = {'fields': {}, 'reasons': ['科目待确认', '上课时间待确认',
                                          '价格单位或金额待确认', '教师要求需本人确认', '公共交通通勤未核实']}
        self.assertEqual(confirmation_heading(order).count('aria-label="待确认"'), 5)
