import http.cookiejar
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from login import QRLogin, protect
from app import DownloadManager


class LoginTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.account = QRLogin(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def begin(self):
        with patch.object(self.account, 'request', return_value={'url': 'https://account.bilibili.com/h5/account-h5/auth/scan-web?x=test', 'qrcode_key': 'fake-key'}):
            result = self.account.begin()
        self.assertTrue(result['qr'].startswith('data:image/svg+xml;base64,'))
        return result

    def success(self):
        self.begin()
        callback = 'https://passport.bilibili.com/crossDomain?SESSDATA=test-secret&bili_jct=test-csrf&DedeUserID=123'
        with patch.object(self.account, 'request', return_value={'code': 0, 'url': callback}):
            return self.account.poll()

    def test_success_encryption_export_logout(self):
        state = self.success()
        self.assertEqual(state['status'], 'logged_in')
        self.assertNotIn('test-secret', json.dumps(state))
        if os.name == 'nt':
            self.assertNotIn(b'test-secret', self.account.saved.read_bytes())
        restarted = QRLogin(self.temp.name)
        path = restarted.export_for_download()
        jar = http.cookiejar.MozillaCookieJar(str(path))
        jar.load(ignore_discard=True)
        self.assertEqual(next(c.value for c in jar if c.name == 'SESSDATA'), 'test-secret')
        path.unlink()
        restarted.logout()
        self.assertFalse(restarted.saved.exists())
        self.assertIsNone(restarted.export_for_download())

    def test_poll_states_and_expiry(self):
        for code, expected in [(86101, 'waiting'), (86090, 'scanned'), (86038, 'expired')]:
            self.begin()
            with patch.object(self.account, 'request', return_value={'code': code}):
                self.assertEqual(self.account.poll()['status'], expected)
        self.begin()
        self.account.deadline = time.monotonic() - 1
        with patch.object(self.account, 'request') as request:
            self.assertEqual(self.account.poll()['status'], 'expired')
            request.assert_not_called()

    def test_poll_rate_limited(self):
        self.begin()
        with patch.object(self.account, 'request', return_value={'code': 86101}) as request:
            self.account.poll()
            self.account.poll()
            self.assertEqual(request.call_count, 1)

    def test_reject_foreign_qr_and_callback(self):
        with patch.object(self.account, 'request', return_value={'url': 'https://evil.test/login', 'qrcode_key': 'fake'}):
            with self.assertRaises(RuntimeError):
                self.account.begin()
        self.begin()
        with patch.object(self.account, 'request', return_value={'code': 0, 'url': 'https://evil.test/?SESSDATA=secret'}):
            with self.assertRaises(RuntimeError):
                self.account.poll()
        self.assertFalse(self.account.saved.exists())

    def test_cookie_header_success(self):
        self.begin()
        cookie = http.cookiejar.Cookie(0, 'SESSDATA', 'header-secret', None, False, '.bilibili.com', True, True, '/', True, True, int(time.time())+1000, False, None, None, {})
        self.account.jar.set_cookie(cookie)
        with patch.object(self.account, 'request', return_value={'code': 0}):
            self.assertEqual(self.account.poll()['status'], 'logged_in')
        path = self.account.export_for_download()
        self.assertIn('header-secret', path.read_text())
        path.unlink()

    def test_download_uses_temporary_cookie_and_removes_it(self):
        self.success()
        manager = DownloadManager(self.account)
        exported = []
        def run(args):
            cookie = Path(args[args.index('--cookies')+1])
            self.assertTrue(cookie.is_file())
            exported.append(cookie)
        with patch('app.resolve_ffmpeg', return_value='ffmpeg'), patch.object(manager, 'run', side_effect=run):
            manager.prepare('https://b23.tv/abc', Path(self.temp.name), '1080', None)
        self.assertEqual(len(exported), 1)
        self.assertFalse(exported[0].exists())

    def test_corrupt_saved_state_is_actionable(self):
        self.account.saved.write_bytes(b'corrupted')
        with self.assertRaisesRegex(RuntimeError, '重新扫码'):
            self.account.export_for_download()


if __name__ == '__main__':
    unittest.main()
