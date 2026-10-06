"""Bilibili QR login. Credentials stay on this computer, encrypted on Windows."""
import base64
import ctypes
from ctypes import wintypes
import http.cookiejar
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import urllib.request
from urllib.parse import urlencode, urlsplit, parse_qs

import qrcode
import qrcode.image.svg


def protect(data, decrypt=False):
    if os.name != 'nt':
        return data
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise OSError('无法读取或保存本机登录凭证，请重新扫码。')
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(target.data)


class QRLogin:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'BilibiliDownloader' / 'account'
        self.saved = self.directory / 'session.dat'
        self.lock = threading.RLock()
        self.jar = http.cookiejar.MozillaCookieJar()
        self.key = None
        self.last_poll = 0
        self.deadline = 0
        self.status = 'saved' if self.saved.is_file() else 'logged_out'
        self.message = '已保存本机登录状态；若失效请重新扫码' if self.saved.is_file() else '未登录；普通视频可直接下载'

    def snapshot(self):
        with self.lock:
            return {'status': self.status, 'message': self.message, 'saved': self.saved.is_file()}

    def request(self, url):
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.bilibili.com/'})
        try:
            with opener.open(request, timeout=15) as response:
                result = json.load(response)
        except Exception:
            raise RuntimeError('连接 B站登录服务失败，请稍后重试。') from None
        if result.get('code') != 0:
            raise RuntimeError('B站登录服务暂不可用，请稍后重试。')
        return result['data']

    def begin(self):
        with self.lock:
            self.jar = http.cookiejar.MozillaCookieJar()
            self.key = None
            self.status, self.message = 'logged_out', '正在获取二维码'
            data = self.request('https://passport.bilibili.com/x/passport-login/web/qrcode/generate')
            url = data.get('url', '')
            parsed = urlsplit(url)
            if parsed.scheme != 'https' or parsed.hostname not in ('passport.bilibili.com', 'account.bilibili.com'):
                raise RuntimeError('B站返回了无法识别的登录地址，请稍后重试。')
            self.key = data['qrcode_key']
            self.deadline = time.monotonic() + 180
            self.last_poll = 0
            qr = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage)
            output = io.BytesIO()
            qr.save(output)
            self.status, self.message = 'waiting', '请用 B站 App 扫一扫，并在手机上确认登录'
            return {**self.snapshot(), 'qr': 'data:image/svg+xml;base64,' + base64.b64encode(output.getvalue()).decode()}

    def poll(self):
        with self.lock:
            if not self.key:
                return self.snapshot()
            now = time.monotonic()
            if now > self.deadline:
                self.key = None
                self.status, self.message = 'expired', '二维码已过期，请点击重新扫码'
                return self.snapshot()
            if now - self.last_poll < 2.5:
                return self.snapshot()
            self.last_poll = now
            data = self.request('https://passport.bilibili.com/x/passport-login/web/qrcode/poll?' + urlencode({'qrcode_key': self.key}))
            code = data.get('code')
            if code == 0:
                # Some responses supply credentials in the Bilibili callback URL.
                parsed = urlsplit(data.get('url', ''))
                values = parse_qs(parsed.query) if parsed.scheme == 'https' and (parsed.hostname == 'bilibili.com' or (parsed.hostname or '').endswith('.bilibili.com')) else {}
                names = {c.name for c in self.jar}
                for name in ('SESSDATA', 'bili_jct', 'DedeUserID', 'DedeUserID__ckMd5'):
                    if name in values and name not in names:
                        self.jar.set_cookie(http.cookiejar.Cookie(0, name, values[name][0], None, False,
                            '.bilibili.com', True, True, '/', True, True, None, True, None, None, {}))
                cookies = [vars(c) for c in self.jar if (c.domain.lstrip('.') == 'bilibili.com' or c.domain.endswith('.bilibili.com')) and not c.is_expired()]
                if not any(c['name'] == 'SESSDATA' for c in cookies):
                    raise RuntimeError('未获取到有效登录状态，请重新扫码。')
                self.directory.mkdir(parents=True, exist_ok=True)
                encrypted = protect(json.dumps(cookies).encode())
                fd, name = tempfile.mkstemp(dir=self.directory, prefix='save-')
                try:
                    with os.fdopen(fd, 'wb') as file:
                        file.write(encrypted)
                    os.replace(name, self.saved)
                finally:
                    Path(name).unlink(missing_ok=True)
                self.key = None
                self.jar.clear()
                self.status, self.message = 'logged_in', '扫码登录成功，下载时自动使用此账号'
            elif code == 86101:
                self.status, self.message = 'waiting', '等待 B站 App 扫码'
            elif code == 86090:
                self.status, self.message = 'scanned', '已扫码，请在手机上确认登录'
            elif code == 86038:
                self.key = None
                self.status, self.message = 'expired', '二维码已过期，请点击重新扫码'
            else:
                raise RuntimeError('登录状态异常，请重新扫码。')
            return self.snapshot()

    def logout(self):
        with self.lock:
            self.key = None
            self.jar.clear()
            self.saved.unlink(missing_ok=True)
            self.status, self.message = 'logged_out', '已清除本机登录状态'
            return self.snapshot()

    def export_for_download(self):
        """Ephemeral worker cookie file; caller must remove it after the worker exits."""
        with self.lock:
            if not self.saved.is_file():
                return None
            try:
                cookies = json.loads(protect(self.saved.read_bytes(), decrypt=True))
                jar = http.cookiejar.MozillaCookieJar()
                for values in cookies:
                    values = dict(values)
                    values['rest'] = values.pop('_rest', {})
                    jar.set_cookie(http.cookiejar.Cookie(**values))
                if not any(c.name == 'SESSDATA' and not c.is_expired() for c in jar):
                    raise ValueError('expired')
                fd, name = tempfile.mkstemp(prefix='download-', suffix='.txt', dir=self.directory)
                os.close(fd)
                try:
                    jar.save(name, ignore_discard=True, ignore_expires=False)
                except Exception:
                    Path(name).unlink(missing_ok=True)
                    raise
                return Path(name)
            except Exception:
                raise RuntimeError('本机登录状态无法读取或已过期，请重新扫码，或清除登录后下载。') from None
