"""Create an isolated environment on first launch, then start the local UI."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
PYTHON = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def main():
    if Path(sys.executable).resolve() != PYTHON.resolve():
        if not PYTHON.exists():
            print('Preparing Python environment...', flush=True)
            subprocess.run([sys.executable, '-m', 'venv', str(ROOT / '.venv')], check=True)
        return subprocess.call([str(PYTHON), str(Path(__file__).resolve())])
    if any(importlib.util.find_spec(name) is None for name in ('yt_dlp', 'imageio_ffmpeg')):
        print('Installing download tools. First launch requires internet access...', flush=True)
        subprocess.run([str(PYTHON), '-m', 'pip', 'install', '-r', str(ROOT / 'requirements.txt')], check=True)
    return subprocess.call([str(PYTHON), str(ROOT / 'app.py')])


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f'Startup failed: {exc}', file=sys.stderr)
        raise SystemExit(1)
