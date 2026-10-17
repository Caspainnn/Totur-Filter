"""Minimal Amap client: location-only requests, private DPAPI key and cache."""
import copy
import ctypes
from ctypes import wintypes
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request
import uuid

ZONE = timezone(timedelta(hours=8))
ORIGIN = '116.288865,40.148278'  # Public, exact 沙河(地铁站) POI validated 2026-10-11.
ENDPOINTS = {'geocode': '/v3/geocode/geo', 'poi': '/v3/place/text', 'transit': '/v3/direction/transit/integrated'}
DISTRICT_NAMES = '门头沟|房山|通州|顺义|大兴|延庆|怀柔|密云|平谷|昌平|海淀|朝阳|东城|西城|丰台|石景山'
LANDMARK_ENDINGS = r'大学|学院|学校|中学|小学|医院|地铁站|火车站|汽车站|公交站|站|小区|社区|公园|展览馆|体育馆|商场|大厦|城|湖|门外|门|东里|西里|南里|北里|里|园|处'
PLACE_ENDINGS = LANDMARK_ENDINGS + r'|家园|花园|公寓|广场|东里|西里|南里|北里|苑|湾|府|庭|阁'
FAILURE_LABELS = {'ADDRESS_INPUT_NOT_SPECIFIC': '缺少可定位地点，通勤待核实',
                  'OUTSIDE_MESSAGE_WINDOW': '不在当前消息时间范围内，暂缓地图查询',
                  'OTHER_CONDITIONS_PENDING': '其他条件仍待确认，暂缓地图查询',
                  'MAP_QUOTA_DEFERRED': '本轮地图额度已用尽，已暂停查询',
                  'MULTIPLE_LOCATIONS': '地图存在多个同名地点，通勤待确认',
                  'ADDRESS_NOT_FOUND': '地图未匹配到具体地点，通勤待确认',
                  'DAILY_LIMIT_REACHED': '地图日请求上限已达，通勤待核实',
                  'MAP_SERVICE_REJECTED': '地图服务未接受请求，通勤待核实',
                  'MAP_QUERY_FAILED': '地图网络或响应失败，通勤待核实',
                  'NO_TRANSIT_ROUTE': '地图未返回公共交通路线，通勤待确认'}


class MapError(RuntimeError):
    pass


def load_private_key(root):
    if os.name != 'nt':
        raise MapError('WINDOWS_KEY_REQUIRED')
    try:
        encrypted = bytes.fromhex((Path(root) / 'amap-key.dpapi').read_text(encoding='utf-8-sig').strip())
        class Blob(ctypes.Structure):
            _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
        buffer = (ctypes.c_ubyte * len(encrypted)).from_buffer_copy(encrypted)
        source, output = Blob(len(encrypted), buffer), Blob()
        crypt = ctypes.WinDLL('crypt32', use_last_error=True)
        crypt.CryptUnprotectData.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        crypt.CryptUnprotectData.restype = wintypes.BOOL
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree.restype = ctypes.c_void_p
        if not crypt.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
            raise ValueError
        try:
            key = ctypes.string_at(output.data, output.size).decode('utf-16-le')
        finally:
            ctypes.memset(output.data, 0, output.size)
            kernel.LocalFree(output.data)
        if not re.fullmatch(r'[a-fA-F0-9]{32}', key):
            raise ValueError
        return key
    except Exception:
        raise MapError('KEY_NOT_AVAILABLE') from None


def sanitize_address(address):
    if not isinstance(address, str) or re.search(r'https?://|www\.', address, re.I):
        return ''
    address = re.split(r'电话|手机|微信|联系人|联系老师|老师|报酬|要求|年级|科目|学生|孩子|姓名|就读|[,，;；。\n]', address)[0]
    address = re.sub(r'(?<!\d)1[3-9]\d{9}(?!\d)', '', address)
    address = re.sub(r'\d+(?:号楼|栋|单元|室)', '', address)
    station = re.fullmatch(r'([\u4e00-\u9fff]{2,20})地铁(?:站)?(?:旁边|附近|旁|周边)\s*\d*\s*米?', address.strip())
    if station and '在' not in station.group(1):
        return station.group(1) + '地铁站'
    address = re.sub(r'[^\u4e00-\u9fffA-Za-z0-9（）()\-]', '', address)
    address = address.strip('，,：: ')
    if '附近' in address:
        prefix, suffix = address.split('附近', 1)
        if suffix and re.fullmatch(r'[\u4e00-\u9fffA-Za-z0-9]{2,30}(?:小区|家园|花园|公寓|苑|园)', suffix):
            district = re.match(r'(?:北京市?)?(?:' + DISTRICT_NAMES + r')区', prefix)
            address = (district.group() if district else '') + suffix
    landmark = re.fullmatch(r'(?:在)?(?P<place>[\u4e00-\u9fffA-Za-z0-9（）()\-]{2,60}?(?:' + LANDMARK_ENDINGS
                            + r'))(?:附近|周边|旁边|这边|这里|那边|那里|门口|旁)(?:约|大约)?\d*(?:米|m)?', address)
    if landmark:
        place = landmark.group('place')
        local_name = re.sub(r'^(?:北京市?)?(?:' + DISTRICT_NAMES + r')区?', '', place)
        if re.fullmatch(LANDMARK_ENDINGS, local_name) or local_name in ('车站', '某大学', '某学校', '某医院'):
            return ''
        return place
    # A named landmark is a usable reference destination, not an exact home.
    address = re.sub(r'(?:这边|这里|那边|那里|附近|周边|旁边|旁)$', '', address)
    if re.fullmatch(LANDMARK_ENDINGS, address) or address in ('车站', '某大学', '某学校', '某医院'):
        return ''
    if len(address) > 100 or not re.search(PLACE_ENDINGS + r'|路|街|胡同|园|村', address):
        return ''
    if re.search(r'附近|某处|周边|待定|面议|任意|不限', address):
        return ''
    places = list(re.finditer(PLACE_ENDINGS, address))
    place = places[-1] if places else None
    if place is None:
        place = re.search(r'路|街|胡同|园|村', address)
    if place:
        end = place.end()
        compound = re.match(r'(?:小区|社区)', address[end:])
        if compound:
            end += len(compound.group())
        street_number = re.match(r'\d+号', address[end:])
        address = address[:end + (len(street_number.group()) if street_number else 0)]
    return address


def normalize_place_name(name):
    name = re.sub(r'[\s（）()·\-]', '', str(name))
    name = re.sub(r'^北京市', '', name)
    return re.sub(r'(?:小区|社区)$', '', name)


def valid_coordinate(coordinate, beijing=True):
    if not isinstance(coordinate, str) or not re.fullmatch(r'\d+(?:\.\d+)?,\d+(?:\.\d+)?', coordinate):
        return False
    lon, lat = map(float, coordinate.split(','))
    return 115.4 <= lon <= 117.6 and 39.4 <= lat <= 41.1 if beijing else 73 <= lon <= 135 and 18 <= lat <= 54


def departure_context(schedule, now):
    current = datetime.fromtimestamp(now, ZONE)
    slot = current.replace(minute=(current.minute // 30) * 30, second=0, microsecond=0) + timedelta(minutes=30)
    reference = {'date': slot.strftime('%Y-%m-%d'), 'time': slot.strftime('%H:%M'), 'verified_schedule': False}
    specified = re.fullmatch(r'\s*(?:每)?(?:周|星期|礼拜)([一二三四五六日天1-7])\s*(上午|下午|晚上|早上|中午)?\s*(\d{1,2})[:：](\d{2})(?:\s*[-~～—至到]\s*\d{1,2}[:：]\d{2})?\s*(?:上课|开始|开课)?\s*', schedule or '')
    if specified is None:
        return reference
    day = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '日': 7, '天': 7, **{str(i): i for i in range(1, 8)}}[specified.group(1)]
    hour, minute = int(specified.group(3)), int(specified.group(4))
    if specified.group(2) in ('下午', '晚上') and hour < 12:
        hour += 12
    if hour > 23 or minute > 59:
        return reference
    target = current.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=(day - current.isoweekday()) % 7)
    if target - timedelta(hours=1) <= current:
        target += timedelta(days=7)
    departure = target - timedelta(hours=1)
    return {'date': departure.strftime('%Y-%m-%d'), 'time': departure.strftime('%H:%M'),
            'class_start': target.strftime('%Y-%m-%d %H:%M'), 'verified_schedule': True}


def write_json(path, value):
    temp = path.with_name(path.name + '-' + uuid.uuid4().hex + '.tmp')
    with temp.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise MapError('REDIRECT_REFUSED')


class MapClient:
    def __init__(self, root, *, key=None, fetch=None, daily_limit=100, city='北京', origin=None):
        from .run_filter import safe_directory
        self.root = safe_directory(Path(root) / 'maps')
        self.key = key if key is not None else load_private_key(root)
        self.fetch = fetch
        self.daily_limit = daily_limit
        if not isinstance(city, str) or not re.fullmatch(r'[\u4e00-\u9fffA-Za-z0-9\s]{1,100}', city):
            raise MapError('ADDRESS_INPUT_NOT_SPECIFIC')
        self.city = city.strip()
        self.beijing = self.city in ('北京', '北京市', '110000', '010')
        self.origin_name = sanitize_address(origin) if origin else None
        if origin and not self.origin_name:
            raise MapError('ADDRESS_INPUT_NOT_SPECIFIC')
        known_origin = self.beijing and (not origin or self.origin_name in ('沙河站', '沙河地铁站', '北京市沙河地铁站'))
        self.origin_coordinate = ORIGIN if known_origin else None
        self.last_request = 0.0
        for old in self.root.glob('route-*.json'):
            if re.fullmatch(r'route-[a-f0-9]{64}\.json', old.name) and time.time() - old.stat().st_mtime > 86400 and not old.is_symlink():
                old.unlink()

    def request(self, endpoint, params, now):
        allowed = {'geocode': {'address', 'city'}, 'poi': {'keywords', 'city', 'citylimit', 'offset'},
                   'transit': {'origin', 'destination', 'city', 'strategy', 'extensions', 'date', 'time'}}
        if endpoint not in ENDPOINTS or not set(params) <= allowed[endpoint]:
            raise MapError('UNSAFE_MAP_REQUEST')
        date = datetime.fromtimestamp(now, ZONE).strftime('%Y-%m-%d')
        usage_path = self.root / 'usage.json'
        try:
            usage = json.loads(usage_path.read_text()) if usage_path.exists() else {'date': date, 'calls': 0}
            if usage['date'] != date:
                usage = {'date': date, 'calls': 0}
            if usage['calls'] >= self.daily_limit:
                raise MapError('DAILY_LIMIT_REACHED')
            usage['calls'] += 1
            write_json(usage_path, usage)
            if self.fetch is not None:
                response = self.fetch(endpoint, dict(params))
            else:
                delay = 0.55 - (time.monotonic() - self.last_request)
                if delay > 0:
                    time.sleep(delay)
                self.last_request = time.monotonic()
                query = urllib.parse.urlencode({**params, 'key': self.key})
                url = 'https://restapi.amap.com' + ENDPOINTS[endpoint] + '?' + query
                opener = urllib.request.build_opener(NoRedirect())
                with opener.open(url, timeout=15) as stream:
                    data = stream.read(2 * 1024 * 1024 + 1)
                if len(data) > 2 * 1024 * 1024:
                    raise MapError('MAP_RESPONSE_TOO_LARGE')
                response = json.loads(data)
            if response.get('status') != '1':
                raise MapError('MAP_SERVICE_REJECTED')
            return response
        except MapError:
            raise
        except Exception:
            # Do not expose URLs: query string contains credential and location.
            raise MapError('MAP_QUERY_FAILED') from None

    def locate(self, clean, now):
        response = self.request('geocode', {'address': clean, 'city': self.city}, now)
        matches = response.get('geocodes', [])
        if response.get('count') == '1' and len(matches) == 1 and matches[0].get('level') in ('兴趣点', '门牌号', '公交地铁站点', '住宅小区', '楼宇') and valid_coordinate(matches[0].get('location'), self.beijing):
            return {'status': 'ok', 'coordinate': matches[0]['location'], 'name': clean}
        response = self.request('poi', {'keywords': clean, 'city': self.city, 'citylimit': 'true', 'offset': '20'}, now)
        region = re.search(DISTRICT_NAMES, clean)
        expected_district = region.group() + '区' if region else None
        requested = normalize_place_name(clean)
        candidates = {}
        for poi in response.get('pois', []):
            name = normalize_place_name(poi.get('name', ''))
            coordinate = poi.get('location', '')
            if len(name) < 3 or not requested.endswith(name) or not valid_coordinate(coordinate, self.beijing):
                continue
            if expected_district and poi.get('adname') != expected_district:
                continue
            if '出入口' in poi.get('type', ''):
                continue
            candidates[coordinate] = poi
        if len(candidates) != 1:
            return {'status': 'ambiguous_address', 'reason': 'MULTIPLE_LOCATIONS' if len(candidates) > 1 else 'ADDRESS_NOT_FOUND'}
        coordinate, poi = next(iter(candidates.items()))
        return {'status': 'ok', 'coordinate': coordinate, 'name': poi['name']}

    def commute(self, address, schedule, now):
        if re.fullmatch(r'线上(?:授课|上课|辅导)?|网课|在线(?:授课|辅导)', address.strip()):
            return {'status': 'ok', 'provider': '线上授课', 'minutes': 0,
                    'walking_meters': 0, 'transfers': 0, 'online': True,
                    'located_name': '线上', 'queried_at': now}
        if re.fullmatch(r'(?:北京市?|海淀区)?(?:北外|北京外国语大学)(?:和|与|、)(?:人大|中国人民大学)中间', address):
            endpoints = [self.commute(place, schedule, now) for place in ('北京外国语大学', '中国人民大学')]
            failure = next((route for route in endpoints if route['status'] != 'ok'), None)
            if failure:
                return failure
            result = copy.deepcopy(max(endpoints, key=lambda route: route['minutes']))
            result.update(located_name='北京外国语大学／中国人民大学两端较长耗时',
                          destination_is_reference=True, reference_method='maximum_of_two_endpoints')
            return result
        clean = sanitize_address(address)
        if not clean:
            return {'status': 'ambiguous_address', 'reason': 'ADDRESS_INPUT_NOT_SPECIFIC'}
        if not self.origin_coordinate:
            if not self.origin_name:
                return {'status': 'ambiguous_address', 'reason': 'ADDRESS_INPUT_NOT_SPECIFIC'}
            located_origin = self.locate(self.origin_name, now)
            if located_origin['status'] != 'ok': return located_origin
            self.origin_coordinate = located_origin['coordinate']
        context = departure_context(schedule, now)
        nearby = bool(re.search(r'这边|这里|那边|那里|附近|周边|旁边|门口', address))
        scope = [clean, context, self.origin_coordinate, nearby, 'poi-v2']
        if not self.beijing: scope.append(self.city)
        fingerprint = hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()
        cache_path = self.root / ('route-' + fingerprint + '.json')
        if cache_path.exists():
            try:
                cached = json.loads(cache_path.read_text(encoding='utf-8'))
                if 0 <= now - cached['queried_at'] < 86400:
                    return cached
            except (ValueError, KeyError):
                pass
        located = self.locate(clean, now)
        if located['status'] != 'ok':
            return located
        coordinate = located['coordinate']
        response = self.request('transit', {'origin': self.origin_coordinate, 'destination': coordinate, 'city': self.city,
                                         'strategy': '0', 'extensions': 'all', 'date': context['date'], 'time': context['time']}, now)
        plans = response.get('route', {}).get('transits', [])
        valid = [p for p in plans if str(p.get('duration', '')).isdigit() and int(p['duration']) > 0]
        if not valid:
            return {'status': 'no_route', 'reason': 'NO_TRANSIT_ROUTE'}
        fastest = min(valid, key=lambda p: int(p['duration']))
        rides = sum(bool(s.get('bus', {}).get('buslines')) or bool(s.get('railway', {}).get('id')) for s in fastest.get('segments', []))
        result = {'status': 'ok', 'provider': '高德', 'minutes': math.ceil(int(fastest['duration']) / 60),
                  'walking_meters': fastest.get('walking_distance'), 'transfers': max(0, rides - 1),
                  'query_departure': context['date'] + ' ' + context['time'], 'class_start': context.get('class_start'),
                  'verified_schedule': context['verified_schedule'], 'queried_at': now,
                  'located_name': located['name'], 'destination_is_reference': nearby}
        write_json(cache_path, result)
        for old in self.root.glob('route-*.json'):
            if re.fullmatch(r'route-[a-f0-9]{64}\.json', old.name) and now - old.stat().st_mtime > 86400 and not old.is_symlink():
                old.unlink()
        return result


def enrich_prioritized(orders, preferences, client, now):
    """Spend quota on otherwise-ready orders, newest local-day messages first."""
    result = copy.deepcopy(orders)
    today = datetime.fromtimestamp(now, ZONE).date()
    def priority(index):
        stamp = max((source['timestamp'] for source in result[index]['sources']), default=0)
        return (datetime.fromtimestamp(stamp, ZONE).date() == today, stamp)
    exhausted = False
    for index in sorted(range(len(result)), key=priority, reverse=True):
        order = result[index]
        if order['type'] != 1 or order['status'] not in ('needs_confirmation', 'recommended'):
            continue
        window = int(preferences.get('message_window_days','7'))
        if max((source['timestamp'] for source in order['sources']),default=0) < now-window*86400:
            order['fields']['commute'] = {'status':'deferred','reason':'OUTSIDE_MESSAGE_WINDOW'}
            continue
        other_conditions = any(reason != '公共交通通勤未核实' for reason in order['reasons'])
        if other_conditions or exhausted:
            order['fields']['commute'] = {'status':'deferred', 'reason':'OTHER_CONDITIONS_PENDING' if other_conditions else 'MAP_QUOTA_DEFERRED'}
            continue
        result[index] = enrich_order(order, preferences, client, now)
        exhausted = result[index]['fields'].get('commute', {}).get('reason') == 'DAILY_LIMIT_REACHED'
    return result


def enrich_order(order, preferences, client, now):
    result = copy.deepcopy(order)
    if result['status'] in ('rejected', 'parse_failed', 'closed') or order['type'] != 1:
        return result
    try:
        route = client.commute(result['fields'].get('address', ''), result['fields'].get('schedule', ''), now)
    except MapError as exc:
        route = {'status': 'query_failed', 'reason': str(exc) if str(exc) in FAILURE_LABELS else 'MAP_QUERY_FAILED'}
    except Exception:
        route = {'status': 'query_failed'}
    result['fields']['commute'] = route
    if route['status'] != 'ok':
        result['reasons'] = [r for r in result['reasons'] if r != '公共交通通勤未核实']
        result['reasons'].append(FAILURE_LABELS.get(route.get('reason'), '地图查询未成功，通勤待确认'))
        return result
    reasons = [r for r in result['reasons'] if r != '公共交通通勤未核实']
    if route['minutes'] > preferences['commute']['maximum_one_way_minutes']:
        reasons.append(f'公共交通单程超过{preferences["commute"]["maximum_one_way_minutes"]:g}分钟')
        result['status'] = 'rejected'
    result['reasons'] = reasons
    if result['status'] != 'rejected':
        result['status'] = 'needs_confirmation' if reasons else 'recommended'
    return result
