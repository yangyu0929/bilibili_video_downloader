"""Check both frozen worker mode and the local HTTP UI of the packaged EXE."""
import json
from pathlib import Path
import queue
import subprocess
import threading
import urllib.request
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / 'dist' / 'BilibiliDownloader' / 'BilibiliDownloader.exe'


def main():
    version = subprocess.run([str(EXE), '--worker', '--version'], capture_output=True, text=True, timeout=45)
    if version.returncode != 0:
        raise RuntimeError(version.stderr)
    print('Packaged yt-dlp:', version.stdout.strip())
    process = subprocess.Popen([str(EXE), '--no-browser'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
    lines = queue.Queue()
    def read_lines():
        for line in process.stdout:
            lines.put(line.strip())
    reader = threading.Thread(target=read_lines, daemon=True)
    reader.start()
    try:
        url = ''
        for _ in range(30):
            line = lines.get(timeout=45)
            if line.startswith('http://127.0.0.1:'):
                url = line
                break
        if not url:
            raise RuntimeError('Packaged app did not report a local URL')
        with urllib.request.urlopen(url, timeout=10) as response:
            assert '开始下载' in response.read().decode('utf-8')
        parsed = urlsplit(url)
        request = urllib.request.Request(f'http://{parsed.netloc}/api/state', headers={'X-App-Token': parse_qs(parsed.query)['token'][0]})
        with urllib.request.urlopen(request, timeout=10) as response:
            assert json.load(response)['status'] == 'idle'
        request = urllib.request.Request(f'http://{parsed.netloc}/api/login/state', headers={'X-App-Token': parse_qs(parsed.query)['token'][0]})
        with urllib.request.urlopen(request, timeout=10) as response:
            assert json.load(response)['status'] in ('saved', 'logged_out')
        print('Packaged UI and authenticated API: OK')
    finally:
        process.terminate()
        process.wait(timeout=10)
        reader.join(timeout=5)
        process.stdout.close()


if __name__ == '__main__':
    main()
