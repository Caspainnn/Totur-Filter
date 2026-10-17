"""Windows deployment contracts, using only synthetic keys and fake run output."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == 'nt', 'Windows DPAPI and PowerShell only')
class DeploymentTests(unittest.TestCase):
    def run_ps(self, command, folder):
        env = dict(os.environ, LOCALAPPDATA=str(folder / 'private'))
        return subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                              cwd=folder, env=env, capture_output=True, text=True)

    def test_key_roundtrip_and_no_accidental_overwrite(self):
        from src.commute import load_private_key
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            shutil.copyfile(ROOT / 'scripts/set_amap_key.ps1', folder / 'set_amap_key.ps1')
            command = "& ./set_amap_key.ps1 -Key (ConvertTo-SecureString ('a' * 32) -AsPlainText -Force)"
            first = self.run_ps(command, folder)
            self.assertEqual(first.returncode, 0, first.stderr)
            private = folder / 'private/WeChatTutorFilter'
            self.assertEqual(load_private_key(private), 'a' * 32)
            encrypted = (private / 'amap-key.dpapi').read_bytes()
            self.assertNotIn(b'a' * 32, encrypted)
            second = self.run_ps(command.replace("'a'", "'b'"), folder)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual((private / 'amap-key.dpapi').read_bytes(), encrypted)
            invalid = self.run_ps(command.replace("'a'", "'z'") + ' -Replace', folder)
            self.assertNotEqual(invalid.returncode, 0)
            self.assertEqual((private / 'amap-key.dpapi').read_bytes(), encrypted)
            replaced = self.run_ps(command.replace("'a'", "'b'") + ' -Replace', folder)
            self.assertEqual(replaced.returncode, 0, replaced.stderr)
            self.assertEqual(load_private_key(private), 'b' * 32)

    def test_portable_entry_and_failed_run_does_not_replace_report(self):
        with tempfile.TemporaryDirectory(prefix='tutor deployment ') as temporary:
            folder = Path(temporary)
            for name in ('scripts', 'src', 'config'):
                (folder / name).mkdir()
            for name in ('run_once_scheduled.ps1', 'export_scheduled_result.ps1'):
                shutil.copyfile(ROOT / 'scripts' / name, folder / 'scripts' / name)
            for name in ('chat_allowlist', 'tutor_preferences', 'tutor_profile'):
                (folder / 'config' / (name + '.json')).write_text('{}', encoding='utf-8')
            (folder / 'src/__init__.py').write_text('', encoding='utf-8')
            (folder / 'src/run_filter.py').write_text(
                "import json,os,sys\nfrom pathlib import Path\n"
                "assert '--no-map' in sys.argv\n"
                "p=Path(os.environ['LOCALAPPDATA'])/'WeChatTutorFilter'/'report.html'\n"
                "p.parent.mkdir(parents=True, exist_ok=True)\np.write_text('synthetic report', encoding='utf-8')\n"
                "print(json.dumps({'status':'OK','generated_at':123,'counts':{},'report':str(p),'map_skipped':True}))\n",
                encoding='utf-8')
            python = sys.executable.replace("'", "''")
            # PowerShell -Command otherwise maps any nonzero script exit to 1.
            command = f"& ./scripts/run_once_scheduled.ps1 -PythonPath '{python}' -NoMap; exit $LASTEXITCODE"
            success = self.run_ps(command, folder)
            self.assertEqual(success.returncode, 0, success.stderr)
            result = json.loads((folder / 'scheduled-once-result.json').read_text(encoding='utf-8-sig'))
            self.assertEqual(result['report'], str(folder / 'tutor-report.html'))
            self.assertEqual((folder / 'tutor-report.html').read_text(), 'synthetic report')
            (folder / 'src/run_filter.py').write_text(
                "import json\nprint(json.dumps({'status':'FAILED','reason':'SYNTHETIC_FAILURE'}))\nraise SystemExit(7)\n",
                encoding='utf-8')
            failure = self.run_ps(command, folder)
            self.assertEqual(failure.returncode, 7, failure.stderr)
            result = json.loads((folder / 'scheduled-once-result.json').read_text(encoding='utf-8-sig'))
            self.assertEqual(result['status'], 'FAILED')
            self.assertEqual((folder / 'tutor-report.html').read_text(), 'synthetic report')
