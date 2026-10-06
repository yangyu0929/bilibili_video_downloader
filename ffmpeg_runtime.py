"""Resolve FFmpeg, fetching the upstream wheel only for portable releases."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import urllib.request
import zipfile


def resolve_ffmpeg(log, cancelled):
    existing = shutil.which('ffmpeg')
    if existing:
        return existing
    if not getattr(sys, 'frozen', False):
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    cache = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'BilibiliDownloader' / 'tools' / 'imageio-ffmpeg-0.6.0'
    binary = cache / 'ffmpeg.exe'
    if binary.is_file():
        return str(binary)
    log('首次使用：正在从 PyPI 获取 FFmpeg（约 31 MB），请稍候…')
    cache.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen('https://pypi.org/pypi/imageio-ffmpeg/0.6.0/json', timeout=30) as response:
        metadata = json.load(response)
    wheel = next(item for item in metadata['urls'] if item['filename'].endswith('win_amd64.whl'))
    if not wheel['url'].startswith('https://files.pythonhosted.org/'):
        raise RuntimeError('合并工具下载地址无效。')
    with tempfile.TemporaryDirectory(prefix='setup-', dir=cache) as temp:
        archive = Path(temp) / 'ffmpeg.whl'
        digest = hashlib.sha256()
        with urllib.request.urlopen(wheel['url'], timeout=30) as response, archive.open('wb') as target:
            while chunk := response.read(1024 * 256):
                if cancelled.is_set():
                    raise RuntimeError('已取消工具下载。')
                digest.update(chunk)
                target.write(chunk)
        if digest.hexdigest() != wheel['digests']['sha256']:
            raise RuntimeError('合并工具校验失败，请重试。')
        with zipfile.ZipFile(archive) as package:
            member = next(name for name in package.namelist() if name.startswith('imageio_ffmpeg/binaries/') and name.endswith('.exe'))
            staged = Path(temp) / 'ffmpeg.exe'
            with package.open(member) as source, staged.open('wb') as target:
                shutil.copyfileobj(source, target)
            for name in package.namelist():
                if 'license' in Path(name).name.lower() and not name.endswith('/'):
                    (cache / Path(name).name).write_bytes(package.read(name))
            if cancelled.is_set():
                raise RuntimeError('已取消工具下载。')
            staged.replace(binary)
    log('合并工具已准备好。')
    return str(binary)
