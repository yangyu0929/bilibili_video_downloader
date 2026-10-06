import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


class InputTests(unittest.TestCase):
    def test_share_text_and_part(self):
        url = 'https://www.bilibili.com/video/BV1xx411c7mD?p=2'
        self.assertEqual(app.normalize_url('分享视频 ' + url + '。'), url)
        self.assertEqual(app.normalize_url('BV1xx411c7mD'), url.split('?')[0])
        self.assertEqual(app.normalize_url('https://b23.tv/hello'), 'https://b23.tv/hello')

    def test_reject_unrelated_urls(self):
        for value in ['https://example.com/a', 'https://bilibili.com.evil.test/video/BV1xx411c7mD',
                      'https://evil@www.bilibili.com/video/BV1xx411c7mD',
                      'https://space.bilibili.com/123', 'not a link',
                      'https://www.bilibili.com:3000/video/BV1xx411c7mD']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                app.normalize_url(value)

    def test_format_and_cookie_arguments(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / '含空格的 folder'
            cookie = Path(temp) / 'cookies.txt'
            args = app.build_command('https://b23.tv/abc', folder, '720', cookie, 'ffmpeg.exe')
            self.assertEqual(args[args.index('-P') + 1], str(folder))
            self.assertEqual(args[args.index('--cookies') + 1], str(cookie))
            self.assertEqual(args[-2:], ['--', 'https://b23.tv/abc'])
            self.assertIn('bv*[height<=720]+ba/b[height<=720]', args)


class WorkerTests(unittest.TestCase):
    def test_real_subprocess_progress_and_result(self):
        manager = app.DownloadManager()
        script = "import json; print('__TITLE__'+json.dumps('测试视频')); print('__PROGRESS__'+json.dumps({'total_bytes':100,'downloaded_bytes':40,'speed':1024,'eta':2})); print('__FILE__'+json.dumps('C:/downloads/test.mp4'))"
        manager.run([sys.executable, '-c', script])
        state = manager.snapshot()
        self.assertEqual(state['status'], 'done')
        self.assertEqual(state['title'], '测试视频')
        self.assertEqual(state['files'], ['C:/downloads/test.mp4'])
        self.assertEqual(state['percent'], 100)

    def test_failure_not_reported_as_success(self):
        manager = app.DownloadManager()
        manager.run([sys.executable, '-c', "import sys; print('ERROR: denied'); sys.exit(1)"])
        self.assertEqual(manager.snapshot()['status'], 'error')
        self.assertIn('ERROR: denied', manager.snapshot()['logs'])

    def test_selected_media_logged(self):
        manager = app.DownloadManager()
        script = "import json; print('__MEDIA__'+json.dumps({'width':1920,'height':1080,'fps':30,'vcodec':'avc1','acodec':'mp4a'}))"
        manager.run([sys.executable, '-c', script])
        self.assertEqual(manager.snapshot()['status'], 'done')
        self.assertIn('avc1', manager.snapshot()['logs'][0])

    def test_cancel_stops_worker(self):
        manager = app.DownloadManager()
        manager.thread = threading.Thread(target=manager.run, args=([sys.executable, '-u', '-c', 'import time; print("started"); time.sleep(30)'],))
        manager.thread.start()
        deadline = time.monotonic() + 5
        while manager.process is None and time.monotonic() < deadline:
            time.sleep(.02)
        manager.cancel()
        manager.thread.join(timeout=10)
        self.assertFalse(manager.thread.is_alive())
        self.assertEqual(manager.snapshot()['status'], 'cancelled')

    def test_duplicate_job_rejected(self):
        manager = app.DownloadManager()
        gate = threading.Event()
        def prepare(*args):
            gate.wait(5)
        with tempfile.TemporaryDirectory() as folder, patch.object(manager, 'prepare', side_effect=prepare):
            data = {'url': 'BV1xx411c7mD', 'output': folder, 'quality': '1080'}
            manager.start(data)
            try:
                with self.assertRaisesRegex(ValueError, '已有下载任务'):
                    manager.start(data)
            finally:
                gate.set()
                manager.thread.join(5)


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.server = app.LocalServer()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(3)

    def request(self, method, path, data=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        connection.request(method, path, json.dumps(data) if data is not None else None, headers or {})
        response = connection.getresponse()
        result = response.status, response.read().decode('utf-8')
        connection.close()
        return result

    def test_ui_and_state(self):
        status, html = self.request('GET', '/?token=' + self.server.token)
        self.assertEqual(status, 200)
        self.assertIn('开始下载', html)
        status, body = self.request('GET', '/api/state', headers={'X-App-Token': self.server.token})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['status'], 'idle')

    def test_auth_host_and_origin(self):
        for headers in [{}, {'X-App-Token': 'wrong'},
                        {'X-App-Token': self.server.token, 'Origin': 'https://evil.test'},
                        {'X-App-Token': self.server.token, 'Host': 'evil.test'}]:
            with self.subTest(headers=list(headers)):
                self.assertEqual(self.request('POST', '/api/start', {}, headers)[0], 403)
        self.assertEqual(self.request('GET', '/')[0], 403)

    def test_bad_input_returns_actionable_error(self):
        status, body = self.request('POST', '/api/start', {'url': 'bad'}, {'X-App-Token': self.server.token})
        self.assertEqual(status, 400)
        self.assertIn('链接', json.loads(body)['error'])


class FormatSelectionTests(unittest.TestCase):
    def select(self, playback, extra=None):
        import yt_dlp
        formats = [
            {'format_id': 'h264', 'height': 1080, 'width': 1920, 'fps': 30, 'vcodec': 'avc1.640028', 'acodec': 'none', 'ext': 'mp4'},
            {'format_id': 'av1', 'height': 1080, 'width': 1920, 'fps': 30, 'vcodec': 'av01.0.08M.08', 'acodec': 'none', 'ext': 'mp4'},
            {'format_id': 'audio', 'vcodec': 'none', 'acodec': 'mp4a.40.2', 'ext': 'm4a'},
        ]
        if extra:
            formats.append(extra)
        for f in formats:
            f['url'] = 'https://example.com/' + f['format_id']
        args = app.build_command('https://b23.tv/abc', Path.cwd(), 'best', None, 'ffmpeg', playback)
        options = {'format': args[args.index('-f') + 1], 'quiet': True, 'no_warnings': True}
        if '-S' in args:
            options['format_sort'] = args[args.index('-S') + 1].split(',')
        with yt_dlp.YoutubeDL(options) as ydl:
            result = ydl.process_ie_result({'id': 'test', 'title': 'test', 'extractor': 'generic', 'formats': formats}, download=False)
        return result['requested_formats'][0]['format_id']

    def test_compatible_selects_h264_source_keeps_default(self):
        self.assertEqual(self.select('compatible'), 'h264')
        self.assertEqual(self.select('source'), 'av1')

    def test_compatible_preserves_4k_when_only_av1_available(self):
        self.assertEqual(self.select('compatible', {'format_id': '4k', 'height': 2160, 'width': 3840, 'fps': 30, 'vcodec': 'av01.0.12M.08', 'acodec': 'none', 'ext': 'mp4'}), '4k')

    def test_mode_has_separate_output_name(self):
        compatible = app.build_command('https://b23.tv/abc', Path.cwd(), 'best', None, 'ffmpeg')
        source = app.build_command('https://b23.tv/abc', Path.cwd(), 'best', None, 'ffmpeg', 'source')
        self.assertNotEqual(compatible[compatible.index('-o') + 1], source[source.index('-o') + 1])


if __name__ == '__main__':
    unittest.main()
