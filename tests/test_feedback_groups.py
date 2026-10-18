import unittest

from src.report import render_key_information


class FeedbackGroupsTests(unittest.TestCase):
    def test_multiple_source_values_have_one_collapsed_action(self):
        order = {'status': 'rejected', 'fields': {},
                 'raw': '科目：数学\n科目：英语\n科目：数学\n薪资：130/h'}
        html = render_key_information(order, '待确认', '待确认')
        self.assertEqual(html.count('<summary>科目不合适'), 1)
        self.assertNotIn('class="feedback-options" open', html)
        self.assertEqual(html.count('data-feedback-field="subject"'), 2)
        self.assertIn('data-feedback-value="数学"', html)
        self.assertIn('data-feedback-value="英语"', html)
        self.assertIn('data-feedback-reason="科目不合适">数学</button>', html)
        self.assertEqual(html.count('data-feedback-field="pay"'), 1)

    def test_closed_orders_have_no_feedback_actions(self):
        html = render_key_information({'status': 'closed', 'fields': {},
                                      'raw': '科目：数学\n科目：英语'}, '', '')
        self.assertNotIn('feedback-reject', html)


if __name__ == '__main__':
    unittest.main()
