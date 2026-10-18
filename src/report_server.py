"""Loopback-only report and fixed settings file API. No WeChat or map calls."""
import argparse
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
from urllib.parse import urlsplit

from .user_settings import validate_user_settings

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 2_000_000


def project_id(root):
    return hashlib.sha256(str(root.resolve()).encode()).hexdigest()


def regular_file(path):
    if path.is_symlink() or (path.exists() and (not path.is_file() or
            getattr(path.lstat(), 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 1024))):
        raise ValueError('Unsafe file')


def read_settings(root):
    path = root / 'manual_closed_orders.json'
    regular_file(path)
    if path.exists() and path.stat().st_size > MAX_BYTES:
        raise ValueError('Too large')
    raw = path.read_bytes() if path.exists() else b''
    settings = validate_user_settings(json.loads(raw.decode('utf-8-sig'))) if raw else {
        'closed_order_keys': [], 'rejection_feedback': [], 'preference_overrides': {}}
    # An existing empty/truncated file must not silently become a fresh file.
    if path.exists() and not raw:
        raise ValueError('Empty settings file')
    return {'revision': hashlib.sha256(raw).hexdigest(), 'settings': settings}


class ReportServer(HTTPServer):
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.token = secrets.token_urlsafe(32)
        super().__init__(('127.0.0.1', 0), ReportHandler)
        self.origin = f'http://127.0.0.1:{self.server_port}'


class ReportHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *args):
        pass

    def respond(self, status, data, content_type='application/json; charset=utf-8'):
        body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=True).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "frame-ancestors 'none'")
        self.send_header('Referrer-Policy', 'no-referrer')
        self.end_headers()
        self.wfile.write(body)

    def allowed(self, api=False, write=False):
        valid = (self.headers.get('Host') == self.server.origin.removeprefix('http://')
                 and self.headers.get('Sec-Fetch-Site') not in ('cross-site',)
                 and self.headers.get('Origin') in (None, self.server.origin))
        if api:
            valid = valid and hmac.compare_digest(self.headers.get('X-Tutor-Token', ''), self.server.token)
        if write:
            valid = valid and self.headers.get('Origin') == self.server.origin
        if not valid:
            self.respond(403, {'error': 'FORBIDDEN'})
        return valid

    def do_GET(self):
        if not self.allowed(api=self.path == '/api/settings'):
            return
        if self.path == '/health':
            self.respond(200, {'project_id': project_id(self.server.root)})
        elif self.path == '/api/settings':
            try:
                self.respond(200, read_settings(self.server.root))
            except (ValueError, RuntimeError, OSError):
                self.respond(409, {'error': 'EXISTING_SETTINGS_INVALID'})
        elif self.path in ('/', '/tutor-report.html'):
            try:
                path = self.server.root / 'tutor-report.html'
                regular_file(path)
                markup = path.read_text(encoding='utf-8-sig')
                markup = markup.replace("default-src 'none';", "default-src 'none'; connect-src 'self';", 1)
                markup = markup.replace('</head>', f'<meta name="tutor-local-token" content="{self.server.token}"></head>', 1)
                self.respond(200, markup.encode('utf-8'), 'text/html; charset=utf-8')
            except (ValueError, OSError):
                self.respond(404, {'error': 'REPORT_NOT_READY'})
        else:
            self.respond(404, {'error': 'NOT_FOUND'})

    def do_POST(self):
        if not self.allowed(api=True, write=True):
            return
        if self.path != '/api/settings':
            self.respond(404, {'error': 'NOT_FOUND'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_BYTES or self.headers.get_content_type() != 'application/json':
                raise ValueError('Invalid request')
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict) or set(payload) != {'revision', 'settings'}:
                raise ValueError('Invalid request')
            data = payload['settings']
            if not isinstance(data, dict) or set(data) - {'version', 'closed_order_keys', 'rejection_feedback', 'preference_overrides'}:
                raise ValueError('Invalid settings')
            settings = validate_user_settings(data)
            if any(set(item) - {'field', 'value', 'reason', 'order_key', 'created_at'} for item in settings['rejection_feedback']):
                raise ValueError('Invalid feedback')
        except (ValueError, RuntimeError, TypeError, OSError):
            self.respond(400, {'error': 'INVALID_SETTINGS'})
            return
        try:
            current = read_settings(self.server.root)
        except (ValueError, RuntimeError, OSError):
            self.respond(409, {'error': 'EXISTING_SETTINGS_INVALID'})
            return
        if payload['revision'] != current['revision']:
            self.respond(409, {'error': 'SETTINGS_CHANGED'})
            return
        temporary = None
        try:
            raw = json.dumps({'version': 2, **settings}, ensure_ascii=False, indent=2).encode('utf-8')
            if len(raw) > MAX_BYTES:
                self.respond(400, {'error': 'SETTINGS_TOO_LARGE'})
                return
            with tempfile.NamedTemporaryFile(dir=self.server.root, prefix='.settings-', suffix='.tmp', delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            target = self.server.root / 'manual_closed_orders.json'
            regular_file(target)
            if read_settings(self.server.root)['revision'] != current['revision']:
                self.respond(409, {'error': 'SETTINGS_CHANGED'})
                return
            os.replace(temporary, target)
            self.respond(200, {'revision': hashlib.sha256(raw).hexdigest(), 'settings': settings})
        except (ValueError, RuntimeError, OSError):
            self.respond(500, {'error': 'SAVE_FAILED'})
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def active_url(root):
    try:
        runtime = json.loads((root / 'report-server.json').read_text(encoding='utf-8'))
        url = runtime['url']
        parsed = urlsplit(url)
        if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or not parsed.port or parsed.path != '/' or parsed.query or parsed.fragment or parsed.username:
            return None
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url + 'health', timeout=1) as response:
            if json.load(response).get('project_id') == project_id(root):
                return url
    except (ValueError, KeyError, OSError):
        pass
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--serve', action='store_true', help='Run the loopback service in the foreground')
    args = parser.parse_args()
    if args.serve:
        server = ReportServer(ROOT)
        runtime = {'url': server.origin + '/', 'pid': os.getpid(), 'project_id': project_id(ROOT)}
        path = ROOT / 'report-server.json'
        regular_file(path)
        path.write_text(json.dumps(runtime), encoding='utf-8')
        try:
            server.serve_forever()
        finally:
            server.server_close()
        return 0
    if not (ROOT / 'tutor-report.html').is_file():
        print(json.dumps({'status': 'FAILED', 'reason': 'REPORT_NOT_READY'}))
        return 1
    url = active_url(ROOT)
    if not url:
        process = subprocess.Popen([sys.executable, '-m', 'src.report_server', '--serve'], cwd=ROOT,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        for _ in range(40):
            time.sleep(0.25)
            url = active_url(ROOT)
            if url or process.poll() is not None:
                break
        if not url:
            if process.poll() is None:
                process.terminate()
            print(json.dumps({'status': 'FAILED', 'reason': 'REPORT_SERVICE_START_FAILED'}))
            return 1
    print(json.dumps({'status': 'OK', 'url': url}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
