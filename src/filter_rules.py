"""Conservative offline rules. Uncertain facts never become a match."""
import copy
import hashlib
import re
import unicodedata
import json
from pathlib import Path
from .user_settings import feedback_rows, normalize_feedback_value, grade_stage
GRADE_STAGE_WORDS = json.loads((Path(__file__).resolve().parents[1] / 'config/extraction_dictionary.json').read_text(encoding='utf-8'))['grade_stages']

NUMBERS = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9,
           **{str(i): i for i in range(1, 10)}}
SUBJECTS = ('数学', '物理', '化学', '生物', '科学', '语文', '英语', '历史', '地理', '政治', '声乐', '音乐', '钢琴', '小提琴', '网球', '游泳', '美术', '书法', '编程', '计算机', '西班牙语', '蒙古语', '日语', '法语', '影子老师')
REASONS = {'commute': '公共交通通勤未核实', 'time': '上课时间待确认'}
OTHER_SCHOOL_ALIASES = ('清华大学', '清华', '北京大学', '北大', '清北', '北京师范大学', '北师大',
                        '北京航空航天大学', '北航', '北京理工大学', '北理工', '中国人民大学', '人大',
                        '北京交通大学', '北交大', '北京科技大学', '北科大', '首都师范大学', '首师大',
                        '北京外国语大学', '北外', '北京语言大学', '北语', '中国传媒大学', '中传',
                        '中央财经大学', '央财', '北京工业大学', '北工大', '北京林业大学', '北林')
NON_TEACHER_LABELS = r'订单|编号|年级(?:性别|科目)?|(?:学生|学员|孩子)[^:：]*|联系地址|授课地址|上课地址|辅导地址|辅导地点|授课地点|上课地点|地址|地点|位置|区域|地区|辅导科目|授课科目|科目|辅导时间|课费报酬|课时费|课费|薪酬|每次时长|每周次数|一周次数|时间次数|报酬|价格|薪资|时间|备注|联系方式|联系电话'
STAGE_TERM = r'(?:大[一二三四1234]|(?:本科|大学)[一二三四1234]年级|本科生|本科在读|本科大学生|研[一二三123]|研究生|硕士|本硕)'
STAGE_CHAIN = STAGE_TERM + r'(?:\s*(?:[、/或和及]|至|到|-)?\s*' + STAGE_TERM + r')*'
NEGATIVE = r'(?:不要|不招|不接受|不考虑|不要求|不需要|排除|谢绝|不收)'
GRADE_LABELS = '补习年级科目|年级性别科目|学员科目|年级性别|年级科目|年级学科|学生年级|辅导年级|年级'
SUBJECT_LABELS = '补习年级科目|年级性别科目|学员科目|辅导科目|授课科目|补习科目|年级科目|年级学科|学科|科目|课程'
TIME_LABELS = '辅导时间|上课时间|授课时间|补习时间|时间安排|工作时间|次数时间|时间次数|每周次数|一周次数|学习频率|每次时长|每次时常|时间段|课次|次数|时间'
PAY_LABELS = '补习薪资|课时薪水|课时报酬|课时价格|老师时薪|老师课费|教员薪酬|辅导时薪|老师薪水|薪资待遇|老师报酬|课费报酬|课时费用|课时费|薪酬|报酬|报价|时薪|薪资|课酬|课费|费用|待遇|价格'
ADDRESS_LABELS = '联系地址|授课地址|上课地址|辅导地址|补习地址|上门地址|学员地址|辅导位置|辅导地点|授课地点|上课地点|工作地点|住址|坐标|地址|地点|位置|区域|地区'
TIME_LABELS = '上课时段|' + TIME_LABELS
PAY_LABELS = '预算范围|' + PAY_LABELS
ADDRESS_LABELS = '上课区域|' + ADDRESS_LABELS
NON_TEACHER_LABELS += '|' + '|'.join((GRADE_LABELS, SUBJECT_LABELS, TIME_LABELS, PAY_LABELS, ADDRESS_LABELS))


def normalize_order(text):
    text = unicodedata.normalize('NFKC', text)
    text = re.sub(r'【([^】]+)】|「([^」]+)」', lambda m: '\n' + (m.group(1) or m.group(2)) + ':', text)
    text = re.sub(r'对(?:老师|教师|教员)(?:的)?要求', '老师要求', text)
    text = re.sub(r':\s*:', ':', text)
    text = re.sub(r'(老师要求|老师报酬)(?!\s*:)\s*', r'\1:', text)
    rows = {int(m.group(1)): m.group(2) for m in re.finditer(r'(?m)^\s*([1-6])[、.．]\s*([^\n]+)', text)}
    if all(number in rows for number in range(1, 7)) and re.search(r'年级|初[一二三]|高[一二三]|幼儿园|\d岁', rows[2]):
        labels = {1: '地址', 2: '年级性别', 3: '科目', 4: '时间', 5: '老师要求', 6: '报酬'}
        text = re.sub(r'(?m)^\s*([1-6])[、.．]\s*([^\n]+)', lambda m: labels[int(m.group(1))] + ':' + m.group(2), text)
    return text


def field_values(text, labels):
    pattern = r'(?:^|[\n,，;；]|(?<=\s))[ \t]*(?:' + labels + r')\s*[:：]\s*([^\n]+)'
    return [m.group(1).strip() for m in re.finditer(pattern, text)]


def schedule_text(text):
    values = field_values(text, TIME_LABELS)
    if not values:
        values = [part for part in re.split(r'[,，;；。\n]', text)
                  if re.search(r'(?<![一每])周[一二三四五六日天末中内]|每周[一二三四五六日天](?!次)|星期|礼拜|工作日', part)]
    value = '；'.join(values)
    value = re.sub(r'周([一二三四五六日天]{2,})', lambda m: '、'.join('周' + day for day in m.group(1)), value)
    value = re.sub(r'周([一二三四五六日天])((?:[,，、]\s*[一二三四五六日天])+)', lambda m: '、'.join('周' + day for day in re.findall(r'[一二三四五六日天]', m.group())), value)
    value = re.sub(r'晚(?=\d)', '晚上', value)
    value = re.sub(r'([一二三四五六七八九])点', lambda m: str(NUMBERS[m.group(1)]) + '点', value)
    value = re.sub(r'(?<!\d)(\d{1,2})[.．](\d{2})(?!\d)', r'\1:\2', value)
    return re.sub(r'([一二三四五六日天])晚(?!上)', r'\1晚上', value)


def address_text(text):
    address = field(text, ADDRESS_LABELS).lstrip(':： ')
    if not address:
        header_address = re.search(r'(?m)^[ \t]*[A-Za-z]{1,4}\d{3,}[ \t]*[#＃]([^\n]+)', text)
        if header_address:
            return address_text('地址：' + header_address.group(1))
    if address:
        address = re.split(r'[,，;；](?=\s*(?:老师|教师|科目|时间|价格|\d+[-~到至]?\d*\s*/h))', address)[0].strip()
        address = re.sub(r'[^\u4e00-\u9fffA-Za-z0-9（）()\-\s,，、]', '', address).strip()
        address = re.sub(r'^(北京市?)在', r'\1', address)
        address = re.sub(r'(?:这边|这里|那边|那里)$', '', address)
        return address
    regions = '门头沟|房山|通州|顺义|大兴|延庆|怀柔|密云|平谷|昌平|海淀|朝阳|东城|西城|丰台|石景山'
    for part in re.split(r'[,，;；。\n]', text):
        part = part.strip(' #/\t')
        if re.match(r'(?:北京市?)?(?:' + regions + r')(?:区)?[^:：]{2,}', part) and not re.search(r'学校|大学生|老师|经验', part):
            return part
    return ''


def subject_text_of(text):
    explicit = field(text, SUBJECT_LABELS)
    if explicit:
        return explicit
    for labels in (GRADE_LABELS, '学生学习情况|学员学习情况|学习情况|学生情况|学员情况'):
        value = field(text, labels)
        if re.search('|'.join(re.escape(s) for s in SUBJECTS) + r'|唱歌|KET|FCE|奥数|语数英|语数外|C\+\+|Python|Scratch', value, re.I):
            return value
    prose = '\n'.join(line for line in text.splitlines() if not re.match(r'\s*(?:' + ADDRESS_LABELS + '|' + PAY_LABELS + r'|备注)\s*:', line))
    return re.split(r'孩子|学生性别|家教经验|地址|有耐心|有经验|在校|师范类|最近开始', prose)[0]


def duration_hours(text):
    number = r'([\d.]+|[一二两三四五六])'
    match = re.search(r'(?:每次时长|每次时常|单次时长|(?:每次|一次|单次)(?:课)?)(?:为|时长)?\s*[:：]?\s*' + number + r'\s*(?:个)?\s*(小时|h\b|分钟)', text, re.I)
    if not match:
        return None
    token, unit = match.groups()
    value = float(token) if re.fullmatch(r'[\d.]+', token) else {'一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5, '六': 6}[token]
    return value / 60 if unit == '分钟' else value


def teacher_requirements(text):
    labels = r'(?:老师|教师|教员)(?:要求|条件|性别|年级|学校|院校|学历)|师资要求'
    collected = []
    active = False
    for line in text.splitlines():
        match = re.search(r'(?:' + labels + r')\s*[:：]?\s*(.*)', line)
        if not match and not collected:
            match = re.match(r'\s*(?:客户)?要求\s*[:：]?\s*(.*)', line)
        if match:
            active = True
            value = re.split(r'(?:^|[ \t,，;；])(?:' + NON_TEACHER_LABELS + r')\s*[:：]', match.group(1), maxsplit=1)[0]
            collected.append(value)
        elif active:
            if re.match(r'\s*(?:' + NON_TEACHER_LABELS + r')\s*[:：]', line):
                active = False
            elif line.strip():
                collected.append(line.strip())
    if not collected:
        collected = [field(text, '要求')]
    if not any(collected):
        role_pattern = r'[男女](?:老师|教师|教员|大学生|研究生)|(?:只要|要求|必须|仅限|要)\s*(?:清北|清华|北大|北航|北邮)|(?:清北|清华|北大|北航|人大).*(?:在校|大学生|研究生|考生)'
        collected = [part.strip() for part in re.split(r'[,，;；。\n]', text)
                     if re.search(role_pattern, part) and not re.search(r'附近|比较近|院内|学生学校|孩子学校', part)]
    return '；'.join(value for value in collected if value).strip('；')


def blocked_district(address, blacklist):
    address = re.split(r'老师|教师|教员|学校|要求|年级|科目|报酬|时间|电话|微信', address)[0]
    explicit = re.findall(r'门头沟区|房山区|通州区|顺义区|大兴区|延庆区|怀柔区|密云区|平谷区|昌平区|海淀区|朝阳区|东城区|西城区|丰台区|石景山区', address)
    if explicit:
        return next((district for district in explicit if district in blacklist), None)
    return next((district for district in blacklist if district.removesuffix('区') in address), None)


def normalize_own_school(requirement, profile):
    aliases = [alias for alias in [profile.get('university', ''), *profile.get('university_aliases', [])] if alias]
    if not aliases:
        return requirement
    names = '|'.join(re.escape(alias) for alias in sorted(aliases, key=len, reverse=True))
    requirement = re.sub(NEGATIVE + r'\s*非\s*(' + names + ')', r'仅限\1', requirement)
    return re.sub(r'非\s*(' + names + r')\s*(?:勿扰|不要|不招|不考虑|不接受|不收)', r'仅限\1', requirement)


def profile_rejections(requirement, profile):
    if not profile or not requirement:
        return []
    requirement = normalize_own_school(requirement, profile)
    # Remove only explicitly negated clauses from positive requirements. Check
    # exclusions of the actual profile separately before this removal.
    active = re.sub(NEGATIVE + r'[^；，,;。]*', '', requirement)
    def preferred(text, end):
        return bool(re.match(r'\s*(?:优先|为佳|最好)', text[end:]))
    rejected = []
    if profile.get('gender') == 'male':
        if re.search(NEGATIVE + r'\s*男(?:老师|教师|教员|生|性)?', requirement):
            rejected.append('教师性别要求不符：不接受男性')
        for clause in re.split(r'[,，;；。]', active):
            unrestricted = re.search(r'男女不限|性别不限|男女均可|男女都可|男女皆可|男生女生都可|男生女生均可|女.*或.*男|男.*或.*女', clause)
            for female in re.finditer(r'女老师|女教师|女教员|女大学生|女研究生|女生|女性|性别\s*[:：]?\s*女|^\s*女(?=专职|在职|在校|全职|兼职|本科|硕士|研究生|大学生|\W|$)', clause):
                if not unrestricted and not preferred(clause, female.end()):
                    rejected.append('教师性别要求不符：仅招女性')
    if profile.get('gender') == 'female':
        if re.search(NEGATIVE + r'\s*女(?:老师|教师|教员|生|性)?', requirement):
            rejected.append('教师性别要求不符：不接受女性')
        for clause in re.split(r'[,，;；。]', active):
            unrestricted = re.search(r'男女不限|性别不限|男女均可|男女都可|男女皆可|男生女生都可|男生女生均可|女.*或.*男|男.*或.*女', clause)
            for male in re.finditer(r'男老师|男教师|男教员|男大学生|男研究生|男生|男性|性别\s*[:：]?\s*男', clause):
                if not unrestricted and not preferred(clause, male.end()) and not re.search(r'最好\s*$', clause[:male.start()]):
                    rejected.append('教师性别要求不符：仅招男性')
    if profile.get('academic_stage') == 'master_1':
        excludes_current = re.search(NEGATIVE + r'\s*(?:研[一1]|研究生|硕士)', requirement)
        stages = [m.group() for m in re.finditer(STAGE_CHAIN, active) if not preferred(active, m.end())]
        stage_text = '；'.join(stages)
        undergraduate = re.search(r'大[一二三四1234]|(?:本科|大学)[一二三四1234]年级|本科生|本科在读|本科大学生', stage_text)
        graduate_years = re.findall(r'研([一二三123])', stage_text)
        graduate_allowed = re.search(r'研究生|硕士|本硕', stage_text)
        lower_bound = re.search(r'(?:大[一二三四1234]|本科)\s*(?:及以上|以上|或以上)', active)
        if excludes_current or (graduate_years and not any(year in ('一', '1') for year in graduate_years)) or (undergraduate and not graduate_allowed and not lower_bound and not any(year in ('一', '1') for year in graduate_years)):
            rejected.append('教师在读年级要求不符：本人研一')
    elif re.fullmatch(r'(?:master|undergraduate)_[1-4]', profile.get('academic_stage', '')):
        stage = profile['academic_stage']
        graduate = stage.startswith('master')
        own_year = int(stage.rsplit('_', 1)[1])
        stage_text = '；'.join(m.group() for m in re.finditer(STAGE_CHAIN, active) if not preferred(active, m.end()))
        graduate_years = [NUMBERS[value] for value in re.findall(r'研([一二三123])', stage_text)]
        undergraduate_years = [NUMBERS[value] for pair in re.findall(r'大([一二三四1234])|(?:本科|大学)([一二三四1234])年级', stage_text) for value in pair if value]
        graduate_allowed = bool(re.search(r'研究生|硕士|本硕', stage_text))
        undergraduate_allowed = bool(re.search(r'大[一二三四1234]|本科|本硕', stage_text))
        lower = re.search(r'大([一二三四1234])\s*(?:及以上|以上|或以上)', active)
        excluded = bool(re.search(NEGATIVE + (r'\s*(?:研究生|硕士|研[' + str(own_year) + next(k for k, v in NUMBERS.items() if v == own_year and not k.isdigit()) + '])' if graduate else r'\s*(?:本科生|本科在读|大[' + str(own_year) + next(k for k, v in NUMBERS.items() if v == own_year and not k.isdigit()) + '])'), requirement))
        if graduate:
            incompatible = bool(graduate_years and own_year not in graduate_years or undergraduate_allowed and not graduate_allowed and not graduate_years and not lower)
        else:
            incompatible = bool(graduate_years or graduate_allowed) and not undergraduate_allowed
            incompatible |= bool(undergraduate_years and own_year not in undergraduate_years and not (lower and own_year >= NUMBERS[lower.group(1)]))
        if excluded or incompatible:
            rejected.append('教师在读年级要求不符：本人' + ('研' if graduate else '大') + str(own_year))
    own_aliases = [profile.get('university', ''), *profile.get('university_aliases', [])]
    own_aliases = [alias for alias in own_aliases if alias]
    if own_aliases:
        own_pattern = '|'.join(re.escape(alias) for alias in own_aliases)
        if re.search(r'(?:不要|不招|不接受|不考虑|排除|非)\s*(?:' + own_pattern + ')|(?:' + own_pattern + r')\s*(?:勿扰|不要|不招|不考虑|不接受)', requirement):
            rejected.append('教师学校要求不符：排除本人学校')
        else:
            school_text = re.sub(r'(?:熟悉|教过|辅导过|有)[^；，,;。]*(?:教材|经验)', '', active)
            unlimited = re.search(r'学校不限|院校不限|不限学校|不限院校|其他学校也可|其他院校也可|任何大学|大学不限', requirement)
            names = sorted(set((*own_aliases, *OTHER_SCHOOL_ALIASES)), key=len, reverse=True)
            pattern = '|'.join(re.escape(name) for name in names)
            named = [m.group() for m in re.finditer(pattern + r'|[\u4e00-\u9fff]{2,12}(?:大学|学院)(?!生)', school_text)
                     if not preferred(school_text, m.end()) and not re.match(r'附中|附小|附属', school_text[m.end():])]
            own_allowed = any(any(alias in name for alias in own_aliases) for name in named)
            named_other = bool(named)
            if named_other and not own_allowed and not unlimited:
                rejected.append('教师学校要求不符：指定其他学校')
    tiers = profile.get('university_tiers', {})
    if tiers and not re.search(r'985本科毕业|本科院校|本科学校|本科毕业院校', requirement):
        alternative = re.search(r'985\s*(?:[/、,，或和]|\s)*211|211\s*(?:[/、,，或和]|\s)*985|985211', active)
        if alternative:
            if not tiers.get('985') and not tiers.get('211'):
                rejected.append('教师院校资质不符：要求985或211')
        else:
            for tier in ('985', '211'):
                for match in re.finditer(r'(?<!\d)' + tier + r'(?!\d)', active):
                    soft = re.match(r'\s*(?:大学生|学生|老师)?\s*优先', active[match.end():])
                    if not soft and tiers.get(tier) is False:
                        rejected.append('教师院校资质不符：要求' + tier)
    return list(dict.fromkeys(rejected))


def requirements_known(requirement, profile, grade=None):
    if not profile:
        return False
    remaining = normalize_own_school(requirement, profile)
    level = grade_stage(grade)
    if level in profile.get('teaching_experience_levels', []):
        remaining = re.sub(r'有(?:家教|教学|授课|辅导)?经验|(?:家教|教学|授课|辅导)经验', '', remaining)
    remaining = re.sub(r'最好(?=[男女](?:老师|教师|教员))', '', remaining)
    for name in sorted(set((profile.get('university', ''), *profile.get('university_aliases', []), *OTHER_SCHOOL_ALIASES)), key=len, reverse=True):
        if not name:
            continue
        remaining = remaining.replace(name, '')
    if re.fullmatch(r'master_[1-3]|undergraduate_[1-4]', profile.get('academic_stage', '')):
        remaining = re.sub(STAGE_CHAIN, '', remaining)
    for tier, membership in profile.get('university_tiers', {}).items():
        if type(membership) is bool:
            remaining = remaining.replace(tier, '')
    remaining = re.sub(r'男老师|男教师|男教员|男生|男性|女老师|女教师|女生|女性|男|女|大学生|学历|性别|学校|院校|年级|在读|要求|只要|仅限|只限|必须|限定|均可|都可|皆可|不限|即可|或|及以上|以上|不要|不招|不接受|不考虑|排除', '', remaining)
    return not re.sub(r'[\W_]+', '', remaining)


def extract_orders(message):
    source = {key: message[key] for key in ('id', 'group_name', 'timestamp')}
    text = message.get('content', '')
    kind = int(message.get('type', 0)) & 0xFFFFFFFF
    if kind == 1 and re.fullmatch(
            r'\s*(?:【(?:订单编号|订单号|编号)】|(?:订单编号|订单号|编号)\s*[:：]?)\s*'
            r'(?:回收|撤回|取消|已接|已出)?\s*[A-Za-z0-9_-]+\s*', text):
        return []  # Bare identifiers/recycling notices contain no tutoring offer.
    if kind in (10000, 10002):
        return []  # Known system messages are not orders.
    if kind == 1 and text.strip() and not re.search(r'家教|辅导|接课|订单|编号|招聘|老师|年级|初[一二三123]|小[一二三四五六123456]|全科|时薪|报酬|课费|' + '|'.join(re.escape(s) for s in SUBJECTS), text):
        return []
    headers = list(re.finditer(r'(?im)^[ \t]*[^\u4e00-\u9fffA-Za-z0-9\n]*(?:(?:订单编号|订单号|编号)\s*[:：]?\s*(?:[^\u4e00-\u9fffA-Za-z0-9\n]|\[[A-Za-z]+\])*[\u4e00-\u9fffA-Za-z0-9-]+|bj\d{4,}|北京(?:家教|线下|线上|[A-Za-z]{0,4})\d{6,}(?:-\d+)?|[A-Z]\d{5,}\s*[:：]|【[^】]+】\d{5,})', text))
    extra_headers = list(re.finditer(r'家教编(?:单|号)\s*[:：]\s*\d{6,}', text))
    extra_headers += list(re.finditer(r'(?m)^[ \t]*(?:[A-Z]{1,4}\d{6,}[ \t]*(?=\r?$)|\d{4,6}[（(]北京[^）)\n]{2,20}[）)])', text))
    extra_headers += list(re.finditer(r'(?m)^[ \t]*[^\u4e00-\u9fffA-Za-z0-9\n]*\d{8}[ \t]*(?=\r?$)', text))
    extra_headers += list(re.finditer(r'(?m)^[ \t]*[A-Za-z]{1,4}\d{3,}[ \t]*[#＃]', text))
    headers = sorted({match.start(): match for match in headers + extra_headers}.values(), key=lambda match: match.start())
    if len(headers) >= 2:
        parts = [text[header.start():headers[i + 1].start() if i + 1 < len(headers) else len(text)] for i, header in enumerate(headers)]
        prefix = text[:headers[0].start()]
        if re.search(r'年级|科目|报酬|/h|元/小时', prefix):
            parts.insert(0, prefix)
        else:
            parts[0] = prefix + parts[0]
    else:
        parts = [text]
        blank_blocks = [block for block in re.split(r'(?:\r?\n)[ \t\r]*(?:\r?\n)+', text) if block.strip()]
        complete_blocks = all(
            field(normalize_order(block), GRADE_LABELS)
            and field(normalize_order(block), SUBJECT_LABELS)
            and field(normalize_order(block), PAY_LABELS)
            for block in blank_blocks)
        if len(blank_blocks) >= 2 and complete_blocks:
            parts = blank_blocks
        numbered = re.split(r'(?m)(?=^\s*\d+[.、)）]\s*(?:小学|小[一二三四五六123456]|初[中一二三123]|高[中一二三123]))', text)
        if len([part for part in numbered if re.match(r'^\s*\d+[.、)）]', part)]) >= 2:
            parts = [part for part in numbered if part.strip()]
        student_headers = list(re.finditer(r'(?m)^[ \t]*学员科目\s*[:：]', text))
        if len(student_headers) >= 2:
            parts = [text[m.start():student_headers[i + 1].start() if i + 1 < len(student_headers) else len(text)] for i, m in enumerate(student_headers)]
            parts[0] = text[:student_headers[0].start()] + parts[0]
    isolated = []
    for part in parts:
        addresses = list(re.finditer(r'(?m)^[ \t]*(?:【(?:' + ADDRESS_LABELS + r')】\s*[:：]?|(?:' + ADDRESS_LABELS + r')\s*[:：])', part))
        if len(addresses) >= 2:
            blocks = [part[m.start():addresses[i + 1].start() if i + 1 < len(addresses) else len(part)] for i, m in enumerate(addresses)]
            complete = all(field(normalize_order(block), GRADE_LABELS) and field(normalize_order(block), SUBJECT_LABELS) and field(normalize_order(block), PAY_LABELS) for block in blocks)
            if complete:
                blocks[0] = part[:addresses[0].start()] + blocks[0]
                isolated.extend(blocks)
                continue
        isolated.append(part)
    return [{'raw': part.strip(), 'type': kind, 'sources': [copy.deepcopy(source)]} for part in isolated]


def field(text, labels):
    values = field_values(text, labels)
    return values[0] if values else ''


def parse_grade(text):
    specified = field(text, GRADE_LABELS) or text
    grades = []
    shared = re.search(r'(?<!\d)([一二三四五六1-6](?:\s*[.、/和及]\s*[一二三四五六1-6])+)(?:年级)', specified)
    if shared:
        grades.extend(NUMBERS[n] for n in re.findall(r'[一二三四五六1-6]', shared[1]))
    for name, code in [('幼儿园小班', -3), ('幼儿园中班', -2), ('幼儿园大班', -1), ('学前班', 0)]:
        if name in specified: grades.append(code)
    for match in re.finditer(r'初中?([一二三123])|高中?([一二三123])|(?:小学)?([一二三四五六七八九123456789])年级|小(?:学)?([一二三四五六123456])(?!\d)', specified):
        junior, senior, primary, short_primary = match.groups()
        grades.append(6 + NUMBERS[junior] if junior else 9 + NUMBERS[senior] if senior else NUMBERS[primary or short_primary])
    if len(set(grades)) > 1:
        return None, True
    if grades:
        return grades[0], False
    if field(text, GRADE_LABELS):
        if re.match(r'成人(?:\s|$|[^\u4e00-\u9fff])', specified): return 14, False
        if re.match(r'大学(?:\s|$|[^\u4e00-\u9fff])', specified): return 13, False
    if re.search(r'幼儿|学前', specified):
        return 'preschool', False
    for stage, words in GRADE_STAGE_WORDS.items():
        if any(word in specified for word in words):
            return stage, False
    return None, False


def parse_pay(text, session_hours=None, explicit_hourly_label=False):
    number = r'(\d+(?:\.\d+)?)(?:\s*[-~～—至到]\s*(\d+(?:\.\d+)?))?'
    per_duration = re.search(number + r'\s*(?:元|块)?\s*/\s*(\d+(?:\.\d+)?)\s*(?:小时|h\b)', text, re.I)
    if per_duration:
        lo, hi, hours = float(per_duration.group(1)), float(per_duration.group(2) or per_duration.group(1)), float(per_duration.group(3))
        return [lo / hours, hi / hours] if hours > 0 and lo <= hi else None
    hourly = re.search(number + r'\s*(?:(?:元|块)\s*(?:/|每|一)?|(?:/|每|一))\s*(?:小时|h\b)', text, re.I)
    if hourly is None:
        hourly = re.search(r'(?:时薪|每小时)\s*[:：]?\s*' + number, text)
    if hourly is None:
        hourly = re.search(number + r'\s*(?:元|块)?\s*时薪', text)
    if hourly is None and explicit_hourly_label:
        abbreviated = re.fullmatch(number + r'\s*h', text.strip(), re.I)
        if abbreviated:
            values = [float(abbreviated.group(1)), float(abbreviated.group(2) or abbreviated.group(1))]
            return values if values[0] <= values[1] else None
    if hourly:
        values = [float(hourly.group(1)), float(hourly.group(2) or hourly.group(1))]
        # A bare duration "2小时" isn't a price; require a pricing label or unit.
        if not re.search(r'报酬|价格|时薪|每小时|课费|薪资|待遇|元|块|/|\d\s*一小时', text):
            return None
        if values[0] > values[1]:
            return None
        return values
    per_class = re.search(number + r'\s*(?:元|块)?\s*(?:/|每|一)\s*次', text)
    hours = session_hours if session_hours is not None else duration_hours(text)
    if per_class and hours is not None:
        if hours <= 0:
            return None
        lo, hi = float(per_class.group(1)), float(per_class.group(2) or per_class.group(1))
        return [lo / hours, hi / hours] if lo <= hi else None
    return None


def interval_result(segment, ranges, session_hours=None, negotiable=False):
    """Require an entire known session to fit one available range; gaps never count."""
    if not ranges:
        return 'conflict'
    matches = list(re.finditer(r'(?<!\d)(\d{1,2})(?:[:：](\d{2})|点(半)?|(?=\s*[-~～至到]\s*\d{1,2}(?:点|:)))', segment))
    times = []
    for match in matches:
        hour, minute = int(match[1]), int(match[2] or (30 if match[3] else 0))
        if hour < 12 and re.search(r'下午|晚上|放学后', segment[:match.start()]):
            hour += 12
        if hour > 24 or minute > 59 or hour == 24 and minute:
            return 'unknown'
        if '点' in match[0] and hour <= 12 and not re.search(r'上午|早上|下午|晚上|中午', segment):
            return 'unknown'
        times.append(hour * 60 + minute)
    if not times:
        if session_hours is not None and not any(
                (int(b[:2])*60+int(b[3:])) - (int(a[:2])*60+int(a[3:])) >= session_hours*60 for a,b in ranges):
            return 'conflict'
        return 'ok' if negotiable else 'unknown'
    if len(times) > 2:
        return 'unknown'
    start = times[0]
    if len(times) > 1:
        # Multiple clocks without a range separator can describe separate sessions.
        between = segment[matches[0].end():matches[1].start()]
        if not re.fullmatch(r'\s*[-~～至到]\s*', between):
            return 'unknown'
        end = times[1]
    else:
        shorthand = re.match(r'\s*[-~～至到]\s*(\d{1,2})(?![\d:：])', segment[matches[0].end():])
        if shorthand:
            end_hour = int(shorthand[1])
            if end_hour < 12 and re.search(r'下午|晚上|放学后', segment[:matches[0].start()]):
                end_hour += 12
            end = end_hour * 60 if end_hour <= 24 else None
        else:
            end = start + session_hours * 60 if session_hours is not None else None
    available = [(int(a[:2])*60+int(a[3:]), int(b[:2])*60+int(b[3:])) for a,b in ranges]
    if end is None:
        return 'unknown' if any(a <= start < b for a,b in available) else 'conflict'
    if end <= start:
        return 'unknown'
    return 'ok' if any(a <= start and end <= b for a,b in available) else 'conflict'


def time_result(text, preferences):
    time_text = schedule_text(text)
    time_text = re.sub(r'(早(?:上)?)(\d{1,2})(?=\s*[-~～至到])', r'\1\2:00', time_text)
    negotiable = preferences['availability'].get('unspecified_class_time') == 'accept_as_negotiable'
    if not time_text:
        return 'ok' if negotiable else 'unknown'
    negotiable_hours = negotiable and not re.search(r'\d{1,2}\s*(?:[:：.．]\s*\d{2}|点)|[一二三四五六七八九十]+点|上午|早上|下午|晚上|中午|放学后|晚\d', time_text)
    if negotiable_hours and not preferences['availability'].get('daily_start') and not preferences['availability'].get('daily_intervals'):
        return 'ok'
    if '或' in time_text:
        options = [part for part in time_text.split('或') if part.strip()]
        results = [time_result('时间：' + part, preferences) for part in options]
        return 'ok' if 'ok' in results else 'unknown' if 'unknown' in results else 'conflict'
    if re.search(r'任选|可选|任意一天', time_text):
        return 'unknown'
    days = []
    for match in re.finditer(r'(?<![一两])(?:周|星期|礼拜)([一二三四五六日天1-7])(?!\s*次)', time_text):
        v = match.group(1)
        days.append(7 if v in ('日', '天', '7') else NUMBERS[v])
    for match in re.finditer(r'(?:周|星期)([一二三四五六])\s*[至到\-~～]\s*(?:周|星期)?([一二三四五六日天])', time_text):
        lo = NUMBERS[match.group(1)]
        hi = 7 if match.group(2) in ('日', '天') else NUMBERS[match.group(2)]
        days.extend(range(lo, hi + 1))
    if '周末' in time_text:
        days.extend((6, 7))
    if '周中' in time_text or '周内' in time_text or '工作日' in time_text:
        days.extend(range(1, 6))
    if re.search(r'每天|每日', time_text):
        days.extend(range(1,8))
    if not days:
        return 'ok' if negotiable_hours else 'unknown'
    availability = preferences['availability']
    full_days = set(availability['weekends']['days']) | set(availability.get('full_day_weekdays', {}).get('days', []))
    restricted = set(availability['weekdays']['days'])
    cutoff_hour, cutoff_minute = map(int, availability['weekdays']['start'].split(':'))
    cutoff = cutoff_hour * 60 + cutoff_minute
    # Each explicit day's time is parsed from its own segment to avoid assigning
    # Wednesday morning's hour to Monday evening in multi-session messages.
    segments = list(re.finditer(r'(?<![一两])(?:周|星期|礼拜)[一二三四五六日天1-7](?!\s*次)(?:\s*[至到\-~～]\s*(?:周|星期|礼拜)?[一二三四五六日天1-7])?|周末|周中|工作日', time_text))
    if len(set(days)) == 1 or len(segments) == 1:
        segments = []
    statuses = []
    for day in sorted(set(days)):
        segment = time_text
        if segments:
            for i, marker in enumerate(segments):
                value = marker.group()
                day_name = '日' if day == 7 else next(k for k, v in NUMBERS.items() if v == day and not k.isdigit())
                span = re.search(r'([一二三四五六日天1-7])\s*[至到\-~～]\s*(?:周|星期|礼拜)?([一二三四五六日天1-7])', value)
                in_range = span and (7 if span.group(1) in '日天' else NUMBERS[span.group(1)]) <= day <= (7 if span.group(2) in '日天' else NUMBERS[span.group(2)])
                if in_range or value.endswith(day_name) or (day == 7 and value.endswith('天')):
                    segment = time_text[marker.start():segments[i + 1].start() if i + 1 < len(segments) else len(time_text)]
                    if re.fullmatch(r'(?:周|星期|礼拜)[一二三四五六日天1-7][\s,，、;；与和]*', segment):
                        segment += time_text[segments[-1].end():]
                    break
        intervals = availability.get('daily_intervals', {})
        if str(day) in intervals:
            statuses.append(interval_result(segment, intervals[str(day)], duration_hours(text), negotiable_hours))
            continue
        daily = availability.get('daily_start', {}).get(str(day))
        if daily == 'all' or daily is None and day in full_days:
            statuses.append('ok')
            continue
        if daily == 'off' or daily is None and day not in restricted:
            statuses.append('conflict')
            continue
        day_cutoff = sum(int(part) * multiplier for part, multiplier in zip(daily.split(':'), (60,1))) if daily else cutoff
        if negotiable_hours:
            statuses.append('ok')
            continue
        explicit = re.search(r'(?<!\d)(\d{1,2})\s*[:：]\s*(\d{2})', segment)
        clock = re.search(r'(?<!\d)(\d{1,2})(?:\s*[-~～至到]\s*\d{1,2})?\s*点', segment)
        if explicit or clock:
            hour = int((explicit or clock).group(1))
            minute = int(explicit.group(2)) if explicit else 30 if re.match(r'\s*半', segment[clock.end():]) else 0
            if ('下午' in segment or '晚上' in segment or '放学后' in segment) and hour < 12:
                hour += 12
            if clock and hour <= 12 and not re.search(r'上午|早上|下午|晚上|中午', segment):
                statuses.append('unknown')
            elif hour > 23 or minute > 59:
                statuses.append('unknown')
            else:
                statuses.append('ok' if hour * 60 + minute >= day_cutoff else 'conflict')
        elif '上午' in segment or '早上' in segment:
            statuses.append('conflict')
        elif '晚上' in segment and day_cutoff <= 18 * 60:
            statuses.append('ok')
        else:
            statuses.append('unknown')
    return 'conflict' if 'conflict' in statuses else 'unknown' if 'unknown' in statuses else 'ok'


def classify_order(order, preferences):
    output = copy.deepcopy(order)
    raw = normalize_order(order['raw'])
    kind = order['type']
    identity = str(kind) + ':' + re.sub(r'\s+', '', raw)
    if kind != 1 or not raw:
        identity += ':' + order['sources'][0]['id']
    output['fingerprint'] = hashlib.sha256(identity.encode()).hexdigest()
    output['fields'] = {}
    rejected, pending = [], []
    if kind != 1 or not raw:
        pending.append('非文本或内容不可解析，需查看微信原消息')
        output.update(status='needs_confirmation', reasons=pending)
        return output
    grade, ambiguous_grade = parse_grade(raw)
    grade_candidates = []
    shared = re.fullmatch(r'(?:小学)?([一二三四五六1-6](?:\s*[.、/和及]\s*[一二三四五六1-6])+)(?:年级)', field(raw,GRADE_LABELS))
    if shared:
        grade_candidates = sorted({NUMBERS[n] for n in re.findall(r'[一二三四五六1-6]', shared[1])})
        grade, ambiguous_grade = 'primary', False
        output['fields']['grade_candidates'] = grade_candidates
        pending.append('包含多个年级，需核对具体授课年级')
        accepted = {parse_grade('年级：'+name)[0] for name in preferences['grades']['accepted']}
        if any(candidate not in accepted for candidate in grade_candidates):
            pending.append('部分授课年级不在可接范围，需确认是否必须同时承担')
    output['fields']['grade'] = grade
    if grade_candidates:
        output['fields']['grade'] = None
    if ambiguous_grade:
        pending.append('包含多个年级，需核对原文')
    if grade is None:
        pending.append('年级待确认')
    elif grade in ('primary', 'preschool', 'junior', 'senior'):
        from .user_settings import GRADE_GROUPS
        names = GRADE_GROUPS[{'primary':'小学','preschool':'幼教','junior':'初中','senior':'高中'}[grade]]
        selected = set(preferences['grades']['accepted']) & set(names)
        if not selected: rejected.append('年级不在用户选择的范围内')
        elif len(selected) < len(names): pending.append('具体学生年级待确认')
    elif grade != 'primary' and grade not in {parse_grade('年级：' + name)[0] for name in preferences['grades']['accepted']}:
        rejected.append('年级不在用户选择的范围内')
    subject_text = subject_text_of(raw)
    english_math = bool(re.search(r'(?:英文|英语)(?:体系|教材|授课)?的?数学|(?:双语|英文授课)数学', subject_text))
    if english_math:
        subject_text = re.sub(r'(?:英文|英语)(?:体系|教材|授课)?的?数学|(?:双语|英文授课)数学', '数学', subject_text)
        output['fields']['instruction_language'] = '英语'
        pending.append('英文授课能力需本人确认')
    subject_text = re.sub(r'语数英|语数外', '语文数学英语', subject_text)
    subject_text = re.sub(r'奥数', '数学', subject_text)
    subject_text = re.sub(r'英文|KET|FCE|剑桥|雅思|托福', '英语', subject_text, flags=re.I)
    subject_text = re.sub(r'中文|汉语', '语文', subject_text)
    subject_text = re.sub(r'唱歌', '声乐', subject_text)
    subject_text = re.sub(r'C\+\+|Python|Scratch', '编程', subject_text, flags=re.I)
    subject_text = re.sub(r'(?:不教|不含|不要|不需要|非)\s*(?:数学|物理|化学|生物|科学|语文|英语)', '', subject_text)
    stage = grade_stage(grade)
    policy = preferences['subjects'].get('by_stage', {}).get(stage, {'mode': 'legacy', 'accepted': []})
    subject_catalog = dict.fromkeys([*SUBJECTS, *policy['accepted'], *(['识字', '拼音', '启蒙'] if policy['mode'] != 'legacy' else [])])
    remaining_subjects, subjects = subject_text, []
    for subject in sorted(subject_catalog, key=len, reverse=True):
        if subject in remaining_subjects:
            subjects.append(subject)
            remaining_subjects = remaining_subjects.replace(subject, ' ')
    output['fields']['subjects'] = subjects
    if re.search(r'各一位|各一名|分别招|分科招',subject_text):
        output['fields']['separate_subject_teachers'] = True
        pending.append('分科各招一位，需确认承接科目')
    primary_companion = (grade == 'primary' or isinstance(grade, int) and 1 <= grade <= 6) and bool(re.search(r'陪伴|陪读', subject_text))
    all_subjects = '全科' in subject_text or ('语文数学英语' in subject_text and '小科目' in raw and '作业辅导' in raw)
    if stage is None and any(item['mode'] != 'legacy' for item in preferences['subjects'].get('by_stage', {}).values()):
        pending.append('学段未明确，科目范围待确认')
    elif policy['mode'] != 'legacy':
        residual = subject_text
        for subject in sorted(subjects, key=len, reverse=True): residual = residual.replace(subject, '')
        residual = re.sub(r'小学|初中|高中|幼儿园|学前班|[一二三四五六七八九0-9]+年级|初[一二三123]|高[一二三123]|男孩|女孩|女生|男生|全科|陪伴|陪读|作业|辅导|补习|课程|文化课|提高|巩固|基础|启蒙|单科|组合|学科', '', residual)
        if re.sub(r'[\W\d_]+', '', residual): pending.append('包含未识别科目，需核对原文')
        if all_subjects:
            output['fields']['subjects'] = ['全科']
            if policy['mode'] != 'any' and '全科' not in policy['accepted']:
                rejected.append('全科不在所选学段的可接科目内')
        elif not subjects and not primary_companion:
            pending.append('科目待确认')
        elif policy['mode'] == 'custom' and not set(subjects or ['小学陪伴']) <= set(policy['accepted']):
            rejected.append('科目不在所选学段的可接科目内')
    elif primary_companion:
        output['fields']['subjects'] = ['小学陪伴']
    elif all_subjects and (grade == 'primary' or isinstance(grade, int) and 1 <= grade <= 6):
        output['fields']['subjects'] = ['小学全科']
    elif all_subjects and grade == 7:
        rejected.append('初一全科超出仅小学全科的范围')
    elif all_subjects:
        pending.append('全科年级或范围待确认')
    elif not subjects:
        pending.append('科目待确认')
    else:
        sciences = set(preferences['subjects']['science_subjects'])
        primary = grade == 'primary' or isinstance(grade, int) and 1 <= grade <= 6
        primary_subjects = set(preferences['subjects'].get('primary_academic_subjects', sciences))
        if primary and set(subjects) <= primary_subjects:
            pass
        elif primary:
            rejected.append('科目不在小学可接受科目内')
        elif any(s in sciences for s in subjects) and any(s not in sciences for s in subjects):
            if grade != 'primary' and not (isinstance(grade, int) and 1 <= grade <= 6):
                pending.append('混合科目要求待确认')
        elif not any(s in sciences for s in subjects):
            rejected.append('科目不符合理科或小学全科')
    prices = field_values(raw, PAY_LABELS)
    pay_text = '；'.join(prices) if prices else '\n'.join(line for line in raw.splitlines() if not re.match(r'\s*(?:备注|之前|原来|过去)', line))
    professional_alternative = re.search(r'(?:如有|如果有|若有|如|如果|若)\s*专职老师', pay_text)
    if professional_alternative and pay_text[:professional_alternative.start()].strip():
        pay_text = pay_text[:professional_alternative.start()].rstrip('，,；; ')
        output['fields']['pay_basis'] = '普通在读老师报价；未采用专职老师另报价'
    if re.search(r'大学生.*专职老师', pay_text):
        pay_text = re.search(r'大学生(.*?)专职老师', pay_text).group(1)
        output['fields']['pay_basis'] = '在读大学生报价'
    duration_parts = field_values(raw, '每次时长|每次时常|单次时长')
    structured_duration = duration_hours('每次时长:' + duration_parts[0]) if duration_parts else duration_hours(schedule_text(raw))
    hourly = parse_pay(pay_text, session_hours=structured_duration,
                       explicit_hourly_label=bool(field(raw, '老师时薪|辅导时薪|时薪')))
    multiple_pay = len(re.findall(r'(?:时薪|每小时)\s*[:：]?\s*\d+(?:\s*[-~至到]\s*\d+)?|\d+(?:\.\d+)?\s*(?:元|块)?\s*(?:/|每|一)\s*(?:\d+(?:\.\d+)?\s*)?(?:小时|次|h\b)', pay_text, re.I)) > 1
    if multiple_pay:
        hourly = None
        pending.append('多种报价或计价方案待确认')
    output['fields']['hourly_cny'] = hourly
    billed = re.search(r'/\s*(\d+(?:\.\d+)?)\s*(?:小时|h\b)', pay_text, re.I)
    output['fields']['billing_hours'] = float(billed.group(1)) if billed else None
    minimum = preferences['pay']['minimum_hourly_cny']
    if hourly is None:
        pending.append('价格单位或金额待确认')
    elif hourly[1] < minimum:
        rejected.append(f'时薪低于{minimum}元')
    elif hourly[0] < minimum and preferences['pay'].get('range_crossing_minimum') != 'accept_if_maximum_meets_minimum':
        pending.append('报价范围跨越最低时薪')
    time_status = time_result(raw, preferences)
    output['fields']['time_status'] = time_status
    output['fields']['schedule'] = schedule_text(raw)
    if time_status == 'conflict':
        rejected.append('上课时间冲突')
    elif time_status == 'unknown':
        pending.append(REASONS['time'])
    output['fields']['address'] = address_text(raw)
    district = blocked_district(output['fields']['address'], preferences.get('location_blacklist', []))
    output['fields']['blocked_district'] = district
    if district:
        rejected.append('授课地点在黑名单：' + district)
    pending.append(REASONS['commute'])
    requirement = teacher_requirements(raw)
    output['fields']['teacher_requirements'] = requirement
    rejected.extend(profile_rejections(requirement, preferences.get('tutor_profile')))
    if requirement and requirement not in ('无', '不限', '无要求') and not requirements_known(requirement, preferences.get('tutor_profile'), grade):
        pending.append('教师要求需本人确认')
    frequency = re.search(r'(?:一周次数|每周次数|一周|每周|周)\s*[:：]?\s*([\d一二三四五六七]+)\s*(?:次|节课|节)', raw)
    output['fields']['weekly_frequency'] = frequency.group(1) if frequency else None
    output['fields']['session_hours'] = duration_hours(raw)
    output.update(status='rejected' if rejected else 'parse_failed' if ambiguous_grade else 'needs_confirmation' if pending else 'recommended',
                  reasons=list(dict.fromkeys(rejected + pending)))
    gender = preferences.get('tutor_profile', {}).get('gender')
    opposite, own = ('女', '男') if gender == 'male' else ('男', '女') if gender == 'female' else (None, None)
    # Legacy setting is accepted on disk, but the profile now drives this built-in rule.
    if opposite is None and preferences.get('pending_female_keyword_rejection'):
        opposite, own = '女', '男'
    if output['status'] == 'needs_confirmation' and opposite and opposite in raw and own not in raw:
        output['status'] = 'rejected'
        output['reasons'].insert(0, f'待确认原文出现“{opposite}”且未同时出现“{own}”')
    values = [(feedback_field, normalize_feedback_value(feedback_field, value)) for _, feedback_field, value in feedback_rows(output['raw'])]
    if output['fields'].get('address'):
        values.append(('address', normalize_feedback_value('address', output['fields']['address'])))
    for feedback in preferences.get('rejection_feedback', []):
        feedback_field, value = feedback['field'], normalize_feedback_value(feedback['field'], feedback['value'])
        if value and (feedback_field, value) in values:
            output['status'] = 'rejected'
            output['reasons'].insert(0, '历史反馈排除：' + feedback['reason'] + '（同字段内容匹配）')
            break
    for closed_id in preferences.get('closed_order_ids', []) + preferences.get('closed_order_keys', []):
        if closed_id == output.get('fingerprint') or re.search(r'(?<![A-Za-z0-9])' + re.escape(closed_id) + r'(?![A-Za-z0-9])', raw):
            output['status'] = 'closed'
            output['fields']['closed_order_id'] = closed_id
            own_feedback = next((item for item in reversed(preferences.get('rejection_feedback', []))
                                 if item['order_key'] == closed_id), None)
            output['reasons'] = [own_feedback['reason'] if own_feedback else '单已被抢走']
            break
    return output


def order_identifier(raw):
    labelled = re.search(r'(?:家教编号|家教编单|订单编号|订单号|编号)\s*[:：]\s*(?:[^\u4e00-\u9fffA-Za-z0-9\n]|\[[A-Za-z]+\])*([A-Za-z\u4e00-\u9fff]*\d+[A-Za-z0-9-]*)', raw)
    if labelled:
        return labelled.group(1)
    header = re.search(r'(?m)^[ \t]*(?:[^\u4e00-\u9fffA-Za-z0-9\n]*)([A-Za-z]{1,4}\d{3,}[A-Za-z0-9-]*|\d{8})(?=[#＃\s]|$)', raw)
    return header.group(1) if header else None


def merge_orders(orders):
    merged = {}
    for order in orders:
        identifier = order_identifier(order['raw'])
        key = 'order:' + identifier if identifier else order['fingerprint']
        if identifier:
            latest = max(source['timestamp'] for source in order['sources'])
            candidate = copy.deepcopy(order)
            candidate['sources'] = [source for source in candidate['sources'] if source['timestamp'] == latest]
            previous = merged.get(key)
            if previous is None or latest >= max(source['timestamp'] for source in previous['sources']):
                if previous and previous['status'] == 'closed':
                    candidate['status'], candidate['reasons'] = 'closed', previous['reasons']
                merged[key] = candidate
            elif candidate['status'] == 'closed':
                previous['status'], previous['reasons'] = 'closed', candidate['reasons']
            continue
        if key not in merged:
            merged[key] = copy.deepcopy(order)
        else:
            known = {(s['id'], s['group_name']) for s in merged[key]['sources']}
            merged[key]['sources'].extend(copy.deepcopy(s) for s in order['sources'] if (s['id'], s['group_name']) not in known)
    return list(merged.values())
