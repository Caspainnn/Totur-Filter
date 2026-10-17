import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from src.commute import sanitize_address, departure_context, enrich_order, MapClient, MapError, normalize_place_name
from src.filter_rules import classify_order, extract_orders

PREF = json.loads((Path(__file__).resolve().parents[1] / 'tests/fixtures/preferences.json').read_text(encoding='utf-8'))


def order():
    message = {'id': 'test', 'group_name': '测试群', 'timestamp': 1791700000, 'type': 1,
               'content': '初一数学100元/小时\n地址：北京市昌平区测试小区\n时间：周三18:00'}
    return classify_order(extract_orders(message)[0], PREF)


class FixedClient:
    def __init__(self, result):
        self.result = result
    def commute(self, address, schedule, now):
        return self.result


class CommuteTests(unittest.TestCase):
    def test_changed_city_and_origin_are_used_with_fake_map(self):
        calls = []
        def fetch(endpoint, params):
            calls.append((endpoint, params))
            if endpoint == 'geocode':
                coordinate = '121.4,31.2' if params['address'] == '示例地铁站' else '121.5,31.3'
                return {'status': '1', 'count': '1', 'geocodes': [{'level': '兴趣点', 'location': coordinate}]}
            return {'status': '1', 'route': {'transits': [{'duration': '1800', 'segments': []}]}}
        with tempfile.TemporaryDirectory() as folder:
            client = MapClient(Path(folder), key='synthetic', fetch=fetch, city='示例城市', origin='示例地铁站')
            self.assertEqual(client.commute('示例小区', '', 1791700000)['status'], 'ok')
            transit = next(params for endpoint, params in calls if endpoint == 'transit')
            self.assertEqual(transit['city'], '示例城市')
            self.assertEqual(transit['origin'], '121.4,31.2')
            self.assertTrue(all(params['city'] == '示例城市' for _, params in calls))
    def test_online_tutoring_passes_without_map_requests(self):
        def forbidden(*args):
            raise AssertionError('Online tutoring must not query maps')
        with tempfile.TemporaryDirectory() as folder:
            client = MapClient(Path(folder), key='synthetic', fetch=forbidden)
            for address in ('线上', '线上授课', '网课', '在线辅导'):
                route = client.commute(address, '', 1791700000)
                self.assertEqual(route['minutes'], 0)
                self.assertTrue(route['online'])
    def test_midpoint_uses_longer_endpoint_as_reference(self):
        class EndpointClient(MapClient):
            def locate(self, clean, now):
                return {'status': 'ok', 'coordinate': '116.3,40.0' if clean == '北京外国语大学' else '116.4,40.0', 'name': clean}
            def request(self, kind, params, now):
                return {'route': {'transits': [{'duration': '2400' if params['destination'] == '116.3,40.0' else '3000', 'segments': []}]}}
        with tempfile.TemporaryDirectory() as folder:
            route = EndpointClient(Path(folder), key='synthetic').commute('北外和人大中间', '', 1791700000)
            self.assertEqual(route['minutes'], 50)
            self.assertTrue(route['destination_is_reference'])
    def test_neighborhood_anchors_and_specific_residence_after_nearby(self):
        cases = {'北京市西城区广安门外': '北京市西城区广安门外',
                 '北京石景山区八大处附近': '北京石景山区八大处',
                 '北京市团结湖': '北京市团结湖', '朝阳区大悦城': '朝阳区大悦城',
                 '朝阳区三源里': '朝阳区三源里', '西城区右安门': '西城区右安门',
                 '朝阳区立水桥附近望春园': '朝阳区望春园'}
        for original, expected in cases.items():
            with self.subTest(address=original):
                self.assertEqual(sanitize_address(original), expected)
    def test_named_landmark_anchors_and_generic_locations(self):
        cases = {'测试大学附近300米': '测试大学', '在测试站附近': '测试站',
                 '海淀区测试医院这边': '海淀区测试医院', '测试学院门口': '测试学院',
                 '测试公园旁边约200米': '测试公园', '测试小区附近': '测试小区'}
        for original, expected in cases.items():
            with self.subTest(address=original):
                self.assertEqual(sanitize_address(original), expected)
        for original in ('大学附近', '海淀区大学附近', '车站附近', '某大学附近', '昌平附近'):
            with self.subTest(address=original):
                self.assertEqual(sanitize_address(original), '')
    def test_only_location_not_contact_details_sent(self):
        self.assertEqual(sanitize_address('海淀测试小区 3号楼2单元101室 电话13800138000'), '海淀测试小区')
        self.assertEqual(sanitize_address('昌平附近'), '')
        self.assertEqual(sanitize_address('https://example.org/电话13800138000'), '')
        self.assertEqual(sanitize_address('北京大学这边'), '北京大学')
        self.assertEqual(normalize_place_name('北京大学'), '北京大学')
        self.assertEqual(sanitize_address('海淀区测试大学附近'), '海淀区测试大学')
        self.assertEqual(sanitize_address('西城区测试展览馆旁边'), '西城区测试展览馆')

    def test_known_class_time_and_reference_context(self):
        timed = departure_context('周三18:00', 1791700000)
        self.assertTrue(timed['verified_schedule'])
        self.assertEqual(timed['time'], '17:00')
        self.assertFalse(departure_context('周末全天', 1791700000)['verified_schedule'])
        self.assertFalse(departure_context('周一18:00或周三18:00', 1791700000)['verified_schedule'])

    def test_duration_boundaries_and_reference(self):
        for minutes, verified, want in [(48, True, 'recommended'), (57, True, 'recommended'),
                                        (61, True, 'rejected'), (48, False, 'recommended'),
                                        (60, False, 'recommended'), (61, False, 'rejected')]:
            with self.subTest(minutes=minutes, verified=verified):
                client = FixedClient({'status': 'ok', 'minutes': minutes, 'verified_schedule': verified})
                self.assertEqual(enrich_order(order(), PREF, client, 1791700000)['status'], want)

    def test_map_error_preserves_order_without_secret(self):
        class Broken:
            def commute(self, *args):
                raise RuntimeError('secret-request-url')
        result = enrich_order(order(), PREF, Broken(), 1791700000)
        self.assertEqual(result['status'], 'needs_confirmation')
        self.assertNotIn('secret-request-url', json.dumps(result))

    def test_ambiguous_geocode_never_selects_first(self):
        def fetch(path, params):
            self.assertNotIn('content', params)
            return {'status': '1', 'geocodes': [{'location': '116,40'}, {'location': '117,40'}], 'count': '2'}
        with tempfile.TemporaryDirectory() as folder:
            client = MapClient(Path(folder), key='synthetic', fetch=fetch)
            result = client.commute('北京测试小区', '周三18:00', 1791700000)
            self.assertEqual(result['status'], 'ambiguous_address')

    def test_quota_limits_real_request_boundary(self):
        with tempfile.TemporaryDirectory() as folder:
            client = MapClient(Path(folder), key='synthetic', fetch=lambda *args: {'status': '1'}, daily_limit=1)
            client.request('geocode', {'address': '测试地点'}, 1791700000)
            with self.assertRaises(MapError):
                client.request('geocode', {'address': '另一个地点'}, 1791700000)

    def test_coarse_geocode_is_not_destination(self):
        with tempfile.TemporaryDirectory() as folder:
            client = MapClient(Path(folder), key='synthetic', fetch=lambda *args: {'status': '1', 'count': '1', 'geocodes': [{'location': '116,40', 'level': '区县'}]})
            self.assertEqual(client.commute('海淀区某处', '周三18:00', 1791700000)['status'], 'ambiguous_address')

    def test_exact_station_precision_and_fastest_route(self):
        def fetch(endpoint, params):
            if endpoint == 'geocode':
                return {'status': '1', 'count': '1', 'geocodes': [{'location': '116.3,40.1', 'level': '公交地铁站点'}]}
            return {'status': '1', 'route': {'transits': [{'duration': '3588', 'segments': []}, {'duration': '2130', 'segments': []}]}}
        with tempfile.TemporaryDirectory() as folder:
            client = MapClient(Path(folder), key='synthetic', fetch=fetch)
            result = client.commute('北京测试地铁站', '周一17:00', 1791700000)
            self.assertEqual(result['minutes'], 36)

    def test_final_http_request_excludes_student_details(self):
        import io
        import urllib.parse
        captured = []
        class Opener:
            def open(self, url, timeout):
                captured.append(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query))
                return io.BytesIO(b'{"status":"1","count":"0","geocodes":[]}')
        with tempfile.TemporaryDirectory() as folder, patch('src.commute.urllib.request.build_opener', return_value=Opener()):
            client = MapClient(Path(folder), key='synthetic')
            client.commute('海淀测试小区，学生张三，就读测试小学', '周三18:00', 1791700000)
            self.assertEqual(captured[0]['address'], ['海淀测试小区'])

    def test_flexible_or_multiple_clocks_are_reference_only(self):
        for schedule in ('周三18:00以后协商', '周三18:00/20:00', '周三上午9:00，晚上18:00'):
            with self.subTest(schedule=schedule):
                self.assertFalse(departure_context(schedule, 1791700000)['verified_schedule'])

    def test_station_nearby_and_named_residential_suffix(self):
        self.assertEqual(sanitize_address('测试北地铁旁边200米'), '测试北地铁站')
        self.assertEqual(sanitize_address('朝阳区测试江湾'), '朝阳区测试江湾')
        self.assertEqual(sanitize_address('海淀知春路测试庄东里'), '海淀知春路测试庄东里')

    def test_poi_fallback_requires_unique_matching_name_and_district(self):
        def fetch(endpoint, params):
            if endpoint == 'geocode':
                return {'status': '1', 'count': '1', 'geocodes': [{'location': '116.4,40.0', 'level': '街道'}]}
            if endpoint == 'poi':
                return {'status': '1', 'pois': [{'name': '测试江湾', 'adname': '朝阳区', 'location': '116.4,40.0', 'type': '商务住宅;住宅区;住宅小区'}]}
            return {'status': '1', 'route': {'transits': [{'duration': '3600', 'walking_distance': '300', 'segments': []}]}}
        with tempfile.TemporaryDirectory() as folder:
            client = MapClient(Path(folder), key='synthetic', fetch=fetch)
            result = client.commute('朝阳区测试江湾', '周三18:00', 1791700000)
            self.assertEqual(result['status'], 'ok')
            self.assertEqual(result['minutes'], 60)
            self.assertEqual(result['located_name'], '测试江湾')

    def test_ambiguous_poi_does_not_choose_first(self):
        def fetch(endpoint, params):
            if endpoint == 'geocode':
                return {'status': '1', 'count': '2', 'geocodes': []}
            return {'status': '1', 'pois': [{'name': '测试花园', 'adname': '海淀区', 'location': '116.3,40.0'}, {'name': '测试花园', 'adname': '海淀区', 'location': '116.4,40.0'}]}
        with tempfile.TemporaryDirectory() as folder:
            result = MapClient(Path(folder), key='synthetic', fetch=fetch).commute('海淀区测试花园', '周三18:00', 1791700000)
            self.assertEqual(result['status'], 'ambiguous_address')
            self.assertEqual(result['reason'], 'MULTIPLE_LOCATIONS')

    def test_map_failure_reason_is_specific_and_safe(self):
        class Limited:
            def commute(self, *args):
                raise MapError('DAILY_LIMIT_REACHED')
        result = enrich_order(order(), PREF, Limited(), 1791700000)
        self.assertIn('地图日请求上限已达，通勤待核实', result['reasons'])
        self.assertNotIn('公共交通通勤未核实', result['reasons'])


if __name__ == '__main__':
    unittest.main()
