# Third-party components

The MIT license applies to this project's own source code. Bundled components
retain their own licenses; it does not relicense those components.

- Python: PSF license, https://docs.python.org/3/license.html
- yt-dlp: Unlicense (with separately licensed dependencies), https://github.com/yt-dlp/yt-dlp
- PyInstaller: GPL-2.0-or-later with a bootloader distribution exception, https://pyinstaller.org/en/stable/license.html
- imageio-ffmpeg (source installation or runtime download): BSD-2-Clause, https://github.com/imageio/imageio-ffmpeg
- FFmpeg (separate runtime dependency, not bundled in releases): build-specific LGPL/GPL terms apply. https://ffmpeg.org/legal.html

The portable archive includes the dependency license and metadata files collected
by PyInstaller. FFmpeg is deliberately excluded from published archives. The
application uses an existing FFmpeg or downloads the upstream imageio-ffmpeg
0.6.0 Windows wheel directly from PyPI on first use, verifying its SHA-256 hash
against PyPI metadata. The downloaded executable and license are cached under
`%LOCALAPPDATA%/BilibiliDownloader/tools/imageio-ffmpeg-0.6.0/`.

To inspect that separately downloaded FFmpeg build, run `ffmpeg.exe -version`,
`ffmpeg.exe -L`, and `ffmpeg.exe -buildconf`. Upstream provenance is tracked at
https://github.com/imageio/imageio-ffmpeg/tree/v0.6.0 and
https://github.com/BtbN/FFmpeg-Builds . If redistributing a modified archive that
bundles FFmpeg, comply with that binary's license and source-distribution terms.
