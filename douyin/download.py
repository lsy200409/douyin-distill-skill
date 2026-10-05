"""yt-dlp 批量下载（--cookies + -i，单条失败不中断）。"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from .cookies import ensure_cookies


def ffmpeg_exe() -> str:
    """优先用 imageio-ffmpeg 自带的静态二进制，找不到再用系统 ffmpeg。"""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        import shutil
        return shutil.which('ffmpeg') or 'ffmpeg'


def _base_cmd(cookies_file: str, out_dir: str, ffmpeg: str):
    return [
        sys.executable, '-m', 'yt_dlp',
        '--cookies', cookies_file,
        '-o', os.path.join(out_dir, '%(title).60s.%(id)s.%(ext)s'),
        '-f', 'bv*[height<=480]+ba/b',  # 480p 上限：蒸馏/转写够用，省流量（要高清可改回 bv*+ba/b）
        '--merge-output-format', 'mp4',
        '--ffmpeg-location', ffmpeg,
        '-i',
    ]


def download_batch(urls_file: str, cookies_file: str, out_dir: str) -> None:
    """按 urls.txt 批量下载。"""
    if not os.path.exists(urls_file):
        print(f'未找到 {urls_file}')
        return
    ensure_cookies(cookies_file)
    os.makedirs(out_dir, exist_ok=True)
    cmd = _base_cmd(cookies_file, out_dir, ffmpeg_exe())
    cmd += ['--batch-file', urls_file]
    print('开始批量下载…')
    subprocess.run(cmd, check=False)


def download_one(url: str, cookies_file: str, out_dir: str) -> None:
    """下载单条视频（最小闭环用）。"""
    ensure_cookies(cookies_file)
    os.makedirs(out_dir, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(url + '\n')
        tmp = f.name
    try:
        cmd = _base_cmd(cookies_file, out_dir, ffmpeg_exe())
        cmd += ['--batch-file', tmp]
        subprocess.run(cmd, check=False)
    finally:
        os.unlink(tmp)
