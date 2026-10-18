import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from src.report_server import ReportServer


class ReportServerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / 'tutor-report.html').write_text(
            '<html><head><meta http-equiv="Content-Security-Policy" content="default-src \'none\';"></head><body>fixture</body></html>',
            encoding='utf-8')
        self.server = ReportServer(self.root)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temporary.cleanup()

    def request(self, method, path, data=None, headers=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        supplied = {'X-Tutor-Token': self.server.token, 'Origin': self.server.origin}
        if data is not None:
            data = json.dumps(data)
            supplied['Content-Type'] = 'application/json'
        supplied.update(headers or {})
        connection.request(method, path, data, supplied)
        response = connection.getresponse()
        status, raw = response.status, response.read()
        connection.close()
        return status, raw

    def test_fixed_destination_and_optimistic_conflict(self):
        status, raw = self.request('GET', '/api/settings')
        self.assertEqual(status, 200)
        initial = json.loads(raw)
        settings = {'closed_order_keys': ['DEMO001'], 'rejection_feedback': [],
                    'preference_overrides': {'pay.minimum_hourly_cny': 130}}
        status, _ = self.request('POST', '/api/settings', {'revision': initial['revision'], 'settings': settings})
        self.assertEqual(status, 200)
        target = self.root / 'manual_closed_orders.json'
        self.assertEqual(json.loads(target.read_text(encoding='utf-8'))['closed_order_keys'], ['DEMO001'])
        before = target.read_bytes()
        status, _ = self.request('POST', '/api/settings', {'revision': initial['revision'], 'settings': settings})
        self.assertEqual(status, 409)
        self.assertEqual(target.read_bytes(), before)

    def test_invalid_or_cross_origin_requests_cannot_write(self):
        initial = json.loads(self.request('GET', '/api/settings')[1])
        invalid = {'revision': initial['revision'], 'settings': {'closed_order_keys': [],
                   'preference_overrides': {'arbitrary.path': 'secret'}}}
        self.assertEqual(self.request('POST', '/api/settings', invalid)[0], 400)
        for headers in ({'Origin': 'https://untrusted.example'}, {'X-Tutor-Token': ''},
                        {'Host': 'untrusted.example'}, {'Sec-Fetch-Site': 'cross-site'}):
            self.assertEqual(self.request('POST', '/api/settings', invalid, headers)[0], 403)
        self.assertFalse((self.root / 'manual_closed_orders.json').exists())
        self.assertEqual(self.request('GET', '/config/tutor_profile.json')[0], 404)
        self.assertEqual(self.request('GET', '/../manual_closed_orders.json')[0], 404)

    def test_bad_existing_json_is_not_overwritten(self):
        target = self.root / 'manual_closed_orders.json'
        target.write_text('broken', encoding='utf-8')
        self.assertEqual(self.request('GET', '/api/settings')[0], 409)
        self.assertEqual(target.read_text(), 'broken')

    def test_report_is_private_and_ready_for_same_origin_save(self):
        status, raw = self.request('GET', '/')
        self.assertEqual(status, 200)
        self.assertIn(self.server.token.encode(), raw)
        self.assertIn(b"connect-src 'self'", raw)
        self.assertEqual(self.request('GET', '/', headers={'Host': 'attacker.example'})[0], 403)
        self.assertEqual(self.server.server_address[0], '127.0.0.1')
