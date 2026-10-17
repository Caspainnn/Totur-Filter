"""Validated local feedback and editable preference overrides; no model calls."""
import copy
import json
from pathlib import Path
import re
import unicodedata

FEEDBACK_FIELDS = {
    'order': ('手动排除', '(?!)'),
    'address': ('地址太远', '联系地址|授课地址|上课地址|辅导地址|补习地址|上门地址|学员地址|辅导位置|辅导地点|授课地点|上课地点|地址|地点|位置'),
    'subject': ('科目不合适', '补习年级科目|年级性别科目|年级科目|年级学科|学员科目|辅导科目|授课科目|补习科目|科目|学科|课程'),
    'student': ('学员不合适', '学生学习情况|学员学习情况|学员本人情况|学生情况|学员情况|学习情况|孩子情况|基本情况|情况'),
    'frequency': ('次数不合适', '每周次数|一周次数|次数时间|时间次数|学习频率|课次|次数|辅导时间|补习时间|上课时间|时间'),
    'duration': ('时长不合适', '每次时长|每次时常|单次时长'),
    'teacher': ('要求不满足', '对老师的要求|对老师要求|对教师的要求|教员要求|老师要求|教师要求|上课要求|要求'),
    'pay': ('薪资不合适', '老师时薪|辅导时薪|教员薪酬|老师报酬|课费报酬|课时费用|课时薪水|课时费|薪酬|薪资|课酬|课费|报酬|报价|时薪|价格'),
}

EDITABLE_PATHS = {
    'message_window_days': 'message_window',
    'pay.minimum_hourly_cny': 'number',
    'pay.range_crossing_minimum': 'range_policy',
    'commute.maximum_one_way_minutes': 'number',
    'preferred_address_keywords': 'strings', 'location_blacklist': 'strings',
    'subjects.primary_academic_subjects': 'strings', 'subjects.science_subjects': 'strings',
    'subjects.by_stage': 'subject_policies',
    'commute.city': 'city', 'commute.origin': 'location',
    'grades.accepted': 'grades',
    'pending_female_keyword_rejection': 'boolean',
    'availability.unspecified_class_time': 'time_policy',
    'availability.weekdays.start': 'clock',
    'availability.weekdays.days': 'days',
    'availability.daily_start': 'daily_start',
    'availability.daily_intervals': 'intervals',
    'availability.full_day_weekdays.days': 'days',
    'availability.weekends.days': 'days',
    'tutor_profile.gender': 'gender',
    'tutor_profile.resume': 'resume',
    'tutor_profile.academic_stage': 'text',
    'tutor_profile.university': 'text',
    'tutor_profile.university_aliases': 'strings',
    'tutor_profile.teaching_experience_levels': 'experience',
    'tutor_profile.university_tiers.211': 'tier',
    'tutor_profile.university_tiers.985': 'tier',
}
GRADE_GROUPS = {
    '幼教': ['幼儿园小班', '幼儿园中班', '幼儿园大班', '学前班'],
    '小学': ['小学' + char + '年级' for char in '一二三四五六'],
    '初中': ['初中' + char + '年级' for char in '一二三'],
    '高中': ['高中' + char + '年级' for char in '一二三'],
    '成人': ['大学', '成人'],
}
GRADE_NAMES = [name for names in GRADE_GROUPS.values() for name in names]
STAGES = ('preschool', 'primary', 'junior', 'senior', 'adult')


def grade_stage(grade):
    if grade in ('junior', 'senior'): return grade
    if grade == 'primary': return 'primary'
    if grade == 'preschool': return 'preschool'
    if isinstance(grade, int):
        return 'preschool' if -3 <= grade <= 0 else 'primary' if 1 <= grade <= 6 else 'junior' if 7 <= grade <= 9 else 'senior' if 10 <= grade <= 12 else 'adult' if grade in (13, 14) else None
    return None


def feedback_rows(raw):
    """Return original line positions and labelled values, never split prose."""
    rows = []
    numbered = {int(match.group(1)): match.group(2) for match in re.finditer(r'(?m)^\s*([1-6])[、.．]\s*([^\n]+)', raw)}
    numeric_template = all(number in numbered for number in range(1, 7)) and bool(re.search(r'年级|初[一二三]|高[一二三]|幼儿园|\d岁', numbered[2]))
    for index, line in enumerate(raw.splitlines()):
        normalized = unicodedata.normalize('NFKC', line).strip()
        normalized = re.sub(r'^[【「]([^】」]+)[】」]\s*[:：]?', r'\1:', normalized)
        number = re.fullmatch(r'([1-6])[、.]\s*(.+)', normalized) if numeric_template else None
        if number:
            name = {1: 'address', 2: 'student', 3: 'subject', 4: 'frequency', 5: 'teacher', 6: 'pay'}[int(number.group(1))]
            rows.append((index, name, number.group(2).strip()))
            continue
        for name, (_, labels) in FEEDBACK_FIELDS.items():
            match = re.fullmatch(r'(?:' + labels + r')\s*[:：]\s*(.+)', normalized)
            if match:
                rows.append((index, name, match.group(1).strip()))
                break
    return rows if len(rows) >= 2 else []


def normalize_feedback_value(field, value):
    value = unicodedata.normalize('NFKC', value)
    if field == 'address':
        from .commute import sanitize_address, normalize_place_name, DISTRICT_NAMES
        clean = sanitize_address(value)
        if clean:
            if clean.endswith('站'):
                clean = re.sub(r'^北京(?=(?:' + DISTRICT_NAMES + r')区?)', '', clean)
                clean = re.sub(r'^(?:北京市)?(?:(?:' + DISTRICT_NAMES + r')区?)?', '', clean)
                clean = re.sub(r'^地铁(?:[一二三四五六七八九十\d]+号线|[\u4e00-\u9fff]{2,8}线)', '', clean)
                clean = re.sub(r'^地铁', '', clean)
                clean = clean.removesuffix('地铁站') + '站' if clean.endswith('地铁站') else clean
            return normalize_place_name(clean)
    return re.sub(r'\s+', '', value)


def validate_overrides(overrides):
    if not isinstance(overrides, dict) or set(overrides) - EDITABLE_PATHS.keys():
        raise RuntimeError('INVALID_PREFERENCE_OVERRIDES')
    choices = {'range_policy': ['accept_if_maximum_meets_minimum', 'needs_confirmation'],
               'time_policy': ['accept_as_negotiable', 'needs_confirmation'],
               'gender': ['male', 'female']}
    for path, value in overrides.items():
        kind = EDITABLE_PATHS[path]
        valid = False
        if kind == 'number':
            valid = type(value) in (int, float) and 0 < value <= 10000
        elif kind == 'message_window':
            valid = isinstance(value,str) and value in ('1','3','5','7')
        elif kind == 'boolean':
            valid = type(value) is bool
        elif kind == 'tier':
            valid = value is None or type(value) is bool
        elif kind == 'text':
            valid = isinstance(value, str) and 0 < len(value) <= 100
        elif kind == 'resume':
            valid = isinstance(value, str) and len(value) <= 20000
        elif kind == 'intervals':
            valid = isinstance(value, dict) and set(value) <= set('1234567')
            if valid:
                for ranges in value.values():
                    if not isinstance(ranges, list) or len(ranges) > 20:
                        valid = False; break
                    previous_end = ''
                    for pair in ranges:
                        if (not isinstance(pair, list) or len(pair) != 2 or not all(isinstance(t, str) for t in pair)
                                or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', pair[0])
                                or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d|24:00', pair[1])
                                or pair[0] >= pair[1] or pair[0] < previous_end):
                            valid = False; break
                        previous_end = pair[1]
        elif kind == 'clock':
            valid = isinstance(value, str) and bool(re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value))
        elif kind == 'daily_start':
            valid = isinstance(value, dict) and set(value) <= set('1234567') and all(
                isinstance(start, str) and (start in ('all','off') or re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', start)) for start in value.values())
        elif kind == 'city':
            valid = isinstance(value, str) and bool(value.strip()) and bool(re.fullmatch(r'[\u4e00-\u9fffA-Za-z0-9\s]{1,100}', value))
        elif kind == 'location':
            from .commute import sanitize_address
            valid = isinstance(value, str) and len(value) <= 100 and bool(sanitize_address(value))
        elif kind == 'subject_policies':
            valid = isinstance(value, dict) and not (set(value) - set(STAGES))
            if valid:
                for policy in value.values():
                    if not isinstance(policy, dict) or set(policy) != {'mode', 'accepted'}:
                        valid = False; break
                    accepted = policy['accepted']
                    valid &= (policy['mode'] in ('legacy', 'any', 'custom') and isinstance(accepted, list)
                              and len(accepted) <= 100 and all(isinstance(s, str) and 0 < len(s) <= 100 for s in accepted)
                              and (policy['mode'] != 'custom' or bool(accepted)))
        elif kind in choices:
            valid = value in choices[kind]
        elif kind in ('strings', 'grades', 'days', 'experience'):
            valid = isinstance(value, list) and len(value) <= 100
            if valid and kind == 'days':
                valid = all(type(item) is int and 1 <= item <= 7 for item in value)
            elif valid:
                valid = all(isinstance(item, str) and 0 < len(item) <= 100 for item in value)
                if kind == 'grades':
                    valid &= bool(value) and set(value) <= set(GRADE_NAMES)
                if kind == 'experience':
                    valid &= set(value) <= set(STAGES)
        if not valid:
            raise RuntimeError('INVALID_PREFERENCE_OVERRIDE_VALUE')
    return overrides


def load_user_settings(path):
    path = Path(path)
    empty = {'closed_order_keys': [], 'rejection_feedback': [], 'preference_overrides': {}}
    if not path.exists():
        return empty
    if path.stat().st_size > 2_000_000:
        raise RuntimeError('USER_SETTINGS_TOO_LARGE')
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict):
        raise RuntimeError('INVALID_MANUAL_CLOSED_ORDERS')
    keys = data.get('closed_order_keys')
    if not isinstance(keys, list) or len(keys) > 10000 or any(
            not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9\u4e00-\u9fff-]{1,100}', key) for key in keys):
        raise RuntimeError('INVALID_MANUAL_CLOSED_ORDERS')
    feedback = data.get('rejection_feedback', [])
    if not isinstance(feedback, list) or len(feedback) > 10000:
        raise RuntimeError('INVALID_REJECTION_FEEDBACK')
    for item in feedback:
        if not isinstance(item, dict) or item.get('field') not in FEEDBACK_FIELDS:
            raise RuntimeError('INVALID_REJECTION_FEEDBACK')
        if (not isinstance(item.get('value'), str) or not 0 < len(item['value']) <= 2000
                or item.get('reason') != FEEDBACK_FIELDS[item['field']][0]
                or not isinstance(item.get('order_key'), str)
                or not re.fullmatch(r'[A-Za-z0-9\u4e00-\u9fff-]{1,100}', item['order_key'])):
            raise RuntimeError('INVALID_REJECTION_FEEDBACK')
    return {'closed_order_keys': sorted(set(keys)), 'rejection_feedback': feedback,
            'preference_overrides': validate_overrides(data.get('preference_overrides', {}))}


def apply_user_settings(preferences, settings):
    result = copy.deepcopy(preferences)
    for path, value in validate_overrides(settings['preference_overrides']).items():
        target = result
        names = path.split('.')
        for name in names[:-1]:
            target = target.setdefault(name, {})
        target[names[-1]] = copy.deepcopy(value)
    result['closed_order_keys'] = settings['closed_order_keys']
    result['rejection_feedback'] = settings['rejection_feedback']
    result['user_preference_overrides'] = settings['preference_overrides']
    return result


def preference_snapshot(preferences):
    values = {}
    for path in EDITABLE_PATHS:
        current = preferences
        for part in path.split('.'):
            current = current.get(part) if isinstance(current, dict) else None
        if current is not None:
            values[path] = current
    return values
