"""Loopback browser preview serving fictional data only, never project files."""
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import base64
import hashlib
import re
import importlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.ui_fixture import write_preview


class Preview(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split('?', 1)[0] != '/':
            self.send_error(404)
            return
        import src.report
        import tests.ui_fixture
        importlib.reload(src.report)
        importlib.reload(tests.ui_fixture)
        with TemporaryDirectory() as directory:
            output = Path(directory) / 'preview.html'
            tests.ui_fixture.write_preview(output)
            markup = output.read_text(encoding='utf-8')
        if self.path == '/?save-test':
            # Test-only file-picker double: real dialogs and private files are never touched.
            harness = '''
window.showDirectoryPicker = undefined;
window.showSaveFilePicker = async () => ({
  getFile: async () => ({size: 100, text: async () => JSON.stringify({version:2,
    closed_order_keys:['external-order'],rejection_feedback:[{order_key:'external-order',field:'address',value:'fictional-external',reason:'地址太远'}],
    preference_overrides:{'pay.minimum_hourly_cny':100}})}),
  createWritable: async () => ({write: async content => {
    let result = document.getElementById('test-save-result');
    if (!result) {result = document.createElement('pre');result.id = 'test-save-result';result.hidden=true;document.body.appendChild(result);}
    result.textContent = content;
  },close: async () => {}})
});
'''
            script = re.search(r'<script type="text/javascript">(.*?)</script>', markup, re.S).group(1)
            combined = harness + script
            digest = base64.b64encode(hashlib.sha256(combined.encode()).digest()).decode()
            markup = re.sub(r"script-src 'sha256-[^']+'", f"script-src 'sha256-{digest}'", markup)
            markup = markup.replace('<script type="text/javascript">', '<script type="text/javascript">' + harness)
        content = markup.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, *args):
        pass


if __name__ == '__main__':
    print('Fictional UI preview only: http://127.0.0.1:8796/', flush=True)
    HTTPServer(('127.0.0.1', 8796), Preview).serve_forever()
