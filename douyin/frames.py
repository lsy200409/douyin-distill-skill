"""用 ffmpeg 从视频中抽取均匀分布的若干帧，供视觉技能(describe.py)分析画面内容。"""
import re
import subprocess
from pathlib import Path

from .download import ffmpeg_exe


def _duration_ffmpeg(ffmpeg: str, video: str) -> float:
    """解析 ffmpeg -i 的 stderr 得到时长(秒)。"""
    r = subprocess.run([ffmpeg, '-i', str(video)], capture_output=True, text=True)
    m = re.search(r'Duration:\s*(\d+):(\d+):([\d.]+)', r.stderr or '')
    if not m:
        return 0.0
    h, mm, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return h * 3600 + mm * 60 + s


def extract_frames(video_dir: str, frames_dir: str, num_frames: int = 8,
                   max_frames: int | None = None) -> int:
    """对 downloads/*.mp4 每个视频抽 num_frames 张均匀帧到 frames/<视频ID>/。

    已存在 jpg 的目录跳过（增量），便于断点续跑。
    """
    ffmpeg = ffmpeg_exe()
    Path(frames_dir).mkdir(parents=True, exist_ok=True)
    n = max_frames or num_frames
    total = 0
    for v in sorted(Path(video_dir).glob('*.mp4')):
        out_dir = Path(frames_dir) / v.stem
        out_dir.mkdir(parents=True, exist_ok=True)
        if any(out_dir.glob('*.jpg')):
            print(f'跳过已抽帧: {v.name}')
            continue
        dur = _duration_ffmpeg(ffmpeg, str(v))
        if dur <= 0:
            times = [0.0]
        else:
            step = dur / n
            times = [round(step * i, 2) for i in range(n)]
        count = 0
        for i, t in enumerate(times, 1):
            out = out_dir / f'f_{i:03d}.jpg'
            subprocess.run(
                [ffmpeg, '-y', '-ss', str(t), '-i', str(v),
                 '-frames:v', '1', '-q:v', '2', str(out)],
                check=False, capture_output=True)
            if out.exists():
                count += 1
        print(f'抽帧: {v.name} -> {count} 张 @ {out_dir}')
        total += count
    return total


def extract_frames_one(video: str, frames_dir: str, num_frames: int = 8) -> int:
    """对单个视频抽均匀帧到 frames/<视频ID>/。已有 jpg 则跳过（增量）。"""
    ffmpeg = ffmpeg_exe()
    Path(frames_dir).mkdir(parents=True, exist_ok=True)
    v = Path(video)
    out_dir = Path(frames_dir) / v.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    if any(out_dir.glob('*.jpg')):
        return 0
    dur = _duration_ffmpeg(ffmpeg, str(v))
    n = max(num_frames, 1)
    if dur <= 0:
        times = [0.0]
    else:
        step = dur / n
        times = [round(step * i, 2) for i in range(n)]
    count = 0
    for i, t in enumerate(times, 1):
        out = out_dir / f'f_{i:03d}.jpg'
        subprocess.run(
            [ffmpeg, '-y', '-ss', str(t), '-i', str(v),
             '-frames:v', '1', '-q:v', '2', str(out)],
            check=False, capture_output=True)
        if out.exists():
            count += 1
    print(f'抽帧: {v.name} -> {count} 张 @ {out_dir}')
    return count
