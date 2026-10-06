"""A loopback-only Bilibili downloader with an authenticated browser UI."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
import webbrowser
from ffmpeg_runtime import resolve_ffmpeg

FROZEN = getattr(sys, 'frozen', False)
ROOT = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
RESOURCES = Path(getattr(sys, '_MEIPASS', ROOT))
CREATE_FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
QUALITIES = {'best': None, '1080': 1080, '720': 720, '480': 480}


def normalize_url(value: str) -> str:
    value = value.strip()
    if re.fullmatch(r'BV[0-9A-Za-z]{10}', value):
        return 'https://www.bilibili.com/video/' + value
    match = re.search(r'https?://[^\s<>"\u3002\uff0c\uff09]+', value)
    if not match:
        raise ValueError('请粘贴完整的视频链接、B站分享文字或 BV 号。')
    url = match.group(0).rstrip(').,;!\u3011')
    parsed = urlsplit(url)
    host = (parsed.hostname or '').lower()
    if parsed.username or parsed.password or parsed.port not in (None, 80, 443):
        raise ValueError('链接包含不支持的地址格式。')
    if host == 'b23.tv':
        if not parsed.path.strip('/'):
            raise ValueError('短链接不完整。')
    elif host == 'bilibili.com' or host.endswith('.bilibili.com'):
        if not re.match(r'^/(video/(BV[0-9A-Za-z]{10}|av\d+)|bangumi/play/(ep|ss)\d+)(?:/|$)', parsed.path):
            raise ValueError('请使用视频页或番剧播放页链接。')
    else:
        raise ValueError('仅支持 bilibili.com 和 b23.tv 视频链接。')
    return url


def build_command(url: str, output: Path, quality: str, cookie: Path | None, ffmpeg: str, playback: str = 'compatible') -> list[str]:
    if playback not in ('compatible', 'source'):
        raise ValueError('不支持的播放兼容选项。')
    height = QUALITIES[quality]
    fmt = f'bv*[height<={height}]+ba/b[height<={height}]' if height else 'bv*+ba/b'
    worker = [sys.executable, '--worker'] if FROZEN else [sys.executable, '-u', '-m', 'yt_dlp']
    args = worker + ['--ignore-config', '--no-playlist',
            '--no-simulate', '--no-quiet', '--newline', '--progress', '--no-color',
            '--socket-timeout', '20', '--retries', '3', '--fragment-retries', '3',
            '--ffmpeg-location', ffmpeg, '--merge-output-format', 'mp4',
            '--windows-filenames', '--no-overwrites', '-f', fmt,
            '-P', str(output), '-o', '%(title).160B [%(id)s]' + (' [compatible]' if playback == 'compatible' else '') + '.%(ext)s',
            '--progress-template', 'download:__PROGRESS__%(progress)j',
            '--print', 'before_dl:__TITLE__%(title)j',
            '--print', 'before_dl:__MEDIA__%(.{width,height,fps,vcodec,acodec})j',
            '--print', 'after_move:__FILE__%(filepath)j']
    if playback == 'compatible':
        args.extend(['-S', 'res,vcodec:h264,fps,acodec:aac'])
    if cookie:
        args.extend(['--cookies', str(cookie)])
    return args + ['--', url]


class DownloadManager:
    def __init__(self):
        self.lock = threading.RLock()
        self.process: subprocess.Popen | None = None
        self.thread: threading.Thread | None = None
        self.cancelled = threading.Event()
        self.state = {'status': 'idle', 'message': '准备就绪', 'percent': 0,
                      'title': '', 'speed': '', 'eta': '', 'files': [], 'logs': []}

    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self.state))

    def update(self, **values):
        with self.lock:
            self.state.update(values)

    def log(self, message):
        with self.lock:
            self.state['logs'] = (self.state['logs'] + [message])[-60:]

    def start(self, data):
        url = normalize_url(str(data.get('url', '')))
        quality = str(data.get('quality', '1080'))
        if quality not in QUALITIES:
            raise ValueError('不支持的清晰度。')
        playback = str(data.get('playback', 'compatible'))
        if playback not in ('compatible', 'source'):
            raise ValueError('不支持的播放兼容选项。')
        output = Path(str(data.get('output', '')).strip() or ROOT / 'downloads').expanduser()
        if not output.is_absolute():
            raise ValueError('保存目录请填写绝对路径。')
        cookie_value = str(data.get('cookie', '')).strip().strip('"')
        cookie = Path(cookie_value).expanduser().resolve() if cookie_value else None
        if cookie and not cookie.is_file():
            raise ValueError('Cookie 文件不存在，请填写 Netscape 格式 cookies.txt 的完整路径。')
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise ValueError('已有下载任务，请等待完成或先取消。')
            output.mkdir(parents=True, exist_ok=True)
            self.cancelled.clear()
            self.state.update(status='running', message='正在解析视频…', percent=0,
                              title='', speed='', eta='', files=[], logs=[])
            self.thread = threading.Thread(target=self.prepare, args=(url, output.resolve(), quality, cookie, playback), daemon=True)
            self.thread.start()

    def prepare(self, url, output, quality, cookie, playback='compatible'):
        try:
            ffmpeg = resolve_ffmpeg(self.log, self.cancelled)
            self.run(build_command(url, output, quality, cookie, ffmpeg, playback))
        except Exception as exc:
            self.log(str(exc))
            self.update(status='cancelled' if self.cancelled.is_set() else 'error',
                        message='已取消' if self.cancelled.is_set() else '合并工具准备失败，请检查网络后重试。')

    def run(self, args):
        process = None
        try:
            with self.lock:
                if self.cancelled.is_set():
                    self.update(status='cancelled', message='已取消')
                    return
                process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                           text=True, encoding='utf-8', errors='replace',
                                           env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
                                           creationflags=CREATE_FLAGS)
                self.process = process
            for raw in process.stdout:
                line = raw.strip()
                if line.startswith('__PROGRESS__'):
                    try:
                        progress = json.loads(line[len('__PROGRESS__'):])
                        total = progress.get('total_bytes') or progress.get('total_bytes_estimate') or 0
                        downloaded = progress.get('downloaded_bytes') or 0
                        speed = progress.get('speed')
                        eta = progress.get('eta')
                        self.update(percent=min(100, downloaded / total * 100) if total else 0,
                                    speed=f'{speed / 1024 / 1024:.2f} MB/s' if speed else '',
                                    eta=f'{int(eta)} 秒' if eta is not None else '',
                                    message='正在合并 / 处理…' if progress.get('status') == 'finished' else '正在下载…')
                    except (ValueError, TypeError):
                        pass
                elif line.startswith('__TITLE__'):
                    self.update(title=json.loads(line[len('__TITLE__'):]))
                elif line.startswith('__MEDIA__'):
                    media = json.loads(line[len('__MEDIA__'):])
                    self.log(f"实际格式：{media.get('width', '?')} × {media.get('height', '?')} / {media.get('fps', '?')} fps；视频 {media.get('vcodec', '?')}；音频 {media.get('acodec', '?')}")
                elif line.startswith('__FILE__'):
                    filename = json.loads(line[len('__FILE__'):])
                    with self.lock:
                        self.state['files'].append(filename)
                elif line:
                    self.log(line)
            code = process.wait()
            if self.cancelled.is_set():
                self.update(status='cancelled', message='已取消；再次下载相同视频可续传。', speed='', eta='')
            elif code == 0:
                self.update(status='done', message='下载完成', percent=100, speed='', eta='')
            else:
                self.update(status='error', message='下载失败，请查看下方日志及使用说明。', speed='', eta='')
        except Exception as exc:
            self.log(str(exc))
            self.update(status='cancelled' if self.cancelled.is_set() else 'error', message='已取消' if self.cancelled.is_set() else '下载失败')
        finally:
            if process:
                if process.poll() is None:
                    self.stop_process(process)
                if process.stdout:
                    process.stdout.close()
            with self.lock:
                self.process = None

    @staticmethod
    def stop_process(process):
        if process.poll() is not None:
            return
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=CREATE_FLAGS, timeout=15)
        else:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

    def cancel(self):
        with self.lock:
            if not self.thread or not self.thread.is_alive():
                return
            self.cancelled.set()
            self.state['message'] = '正在取消…'
            process = self.process
        if process:
            self.stop_process(process)


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port=0):
        super().__init__(('127.0.0.1', port), Handler)
        self.token = secrets.token_urlsafe(32)
        self.origin = f'http://127.0.0.1:{self.server_port}'
        self.manager = DownloadManager()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def reply(self, status, data, content_type='application/json; charset=utf-8'):
        body = data.encode('utf-8') if isinstance(data, str) else json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(body)

    def authorized(self):
        if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}':
            return False
        if self.headers.get('Origin') not in (None, self.server.origin):
            return False
        candidate = self.headers.get('X-App-Token', '')
        return secrets.compare_digest(candidate, self.server.token)

    def do_GET(self):
        parsed = urlsplit(self.path)
        if parsed.path == '/':
            token = parse_qs(parsed.query).get('token', [''])[0]
            if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}' or not secrets.compare_digest(token, self.server.token):
                self.reply(403, {'error': '请从启动窗口中的完整链接打开界面。'})
                return
            html = (RESOURCES / 'index.html').read_text(encoding='utf-8')
            self.reply(200, html, 'text/html; charset=utf-8')
        elif parsed.path == '/api/state' and self.authorized():
            self.reply(200, {**self.server.manager.snapshot(), 'default_output': str(ROOT / 'downloads')})
        else:
            self.reply(403, {'error': '请求未授权。'})

    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 16384:
                raise ValueError('请求大小无效。')
            body = self.rfile.read(length)
            if not self.authorized():
                self.reply(403, {'error': '请求未授权，请重新启动程序。'})
                return
            data = json.loads(body)
            if not isinstance(data, dict):
                raise ValueError('请求格式无效。')
            if self.path == '/api/start':
                self.server.manager.start(data)
            elif self.path == '/api/cancel':
                self.server.manager.cancel()
            else:
                self.reply(404, {'error': '地址不存在。'})
                return
            self.reply(200, {'ok': True})
        except (ValueError, OSError, RuntimeError) as exc:
            self.reply(400, {'error': str(exc)})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args()
    server = LocalServer(args.port)
    url = f'{server.origin}/?token={server.token}'
    print(f'Bilibili Downloader\n{url}\nKeep this window open. Press Ctrl+C to stop.', flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        pass
    finally:
        server.manager.cancel()
        if server.manager.thread:
            server.manager.thread.join(timeout=8)
        server.server_close()


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--worker':
        import yt_dlp
        yt_dlp.main(sys.argv[2:])
    else:
        main()
