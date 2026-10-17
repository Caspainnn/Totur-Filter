"""Anonymous, fictional orders for browser verification. No project settings."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
from src.report import render_report


def write_preview(path):
    now = int(datetime(2026, 10, 14, 15, 45, tzinfo=timezone(timedelta(hours=8))).timestamp())
    orders = []
    statuses = ['needs_confirmation'] * 5 + ['recommended'] * 2 + ['closed', 'rejected', 'parse_failed']
    for index, status in enumerate(statuses):
        grade = [5, 4, 7, 6, 3][index % 5]
        subject = '物理' if grade == 7 else '数学'
        schedule = '周六，具体钟点待确认' if status == 'needs_confirmation' else '周六14:00–16:00'
        raw = (f'编号：DEMO{index + 1:03}\n科目：{grade}年级{subject}\n时间：{schedule}\n'
               f'报价：{120 + index * 10}元/小时\n教师要求：有小学辅导经验\n地址：示例区域{chr(65 + index)}')
        if status == 'parse_failed': raw = '无法识别的匿名示例文本 <script>测试转义</script>'
        orders.append({'status': status, 'raw': raw, 'fingerprint': f'demo-{index}',
            'fields': {'grade': grade, 'subjects': [subject], 'hourly_cny': [120 + index * 10, 120 + index * 10],
                       'address': f'示例区域{chr(65 + index)}', 'schedule': schedule,
                       'teacher_requirements': '有小学辅导经验',
                       'commute': {'status': 'ok', 'minutes': 38 + index, 'transfers': 1, 'walking_meters': 600,
                                   'query_departure': '2026-10-17 13:00', 'verified_schedule': False}},
            'reasons': ['上课时间未明确，需核对原文'] if status == 'needs_confirmation' else ['报价低于设定下限'] if status == 'rejected' else [],
            'sources': [{'group_name': '匿名示例群', 'timestamp': now - 1500 - index * 600}]})
    preferences = {'pay.minimum_hourly_cny': 100, 'commute.maximum_one_way_minutes': 60,
        'commute.city': '示例城市', 'commute.origin': '示例地铁站',
        'subjects.primary_academic_subjects': ['语文','数学','英语','科学'],
        'subjects.science_subjects': ['数学','物理','化学','生物','科学'],
        'grades.accepted': ['小学一年级', '小学五年级', '初中一年级'],
        'availability.weekdays.start': '17:00', 'availability.weekdays.days': [1, 2, 4],
        'availability.full_day_weekdays.days': [3, 5], 'availability.weekends.days': [6, 7],
        'pay.range_crossing_minimum': 'accept_if_maximum_meets_minimum',
        'availability.unspecified_class_time': 'accept_as_negotiable',
        'tutor_profile.gender': 'male', 'tutor_profile.academic_stage': 'master_1',
        'tutor_profile.university': '示例大学', 'preferred_address_keywords': ['示例区域B']}
    metadata = {'generated_at': now, 'new_orders': len(orders), 'messages_read': len(orders),
        'ui_preferences': preferences, 'preferred_address_keywords': ['示例区域B'],
        'rejection_feedback': [{'order_key': 'demo-rule', 'field': 'pay', 'value': '80元/小时', 'reason': '薪资不合适'}],
        'closed_order_keys': [], 'preference_overrides': {}}
    Path(path).write_text(render_report(orders, metadata), encoding='utf-8', newline='\n')


if __name__ == '__main__':
    write_preview(Path(__file__).resolve().parents[1] / 'ui-preview.html')
