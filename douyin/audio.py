"""ffmpeg 批量剥音频（mp4 -> mp3）。"""
import subprocess
from pathlib import Path

from .download import ffmpeg_exe


def extract_audio(video_dir: str, audio_dir: str) -> int:
    """把 downloads/*.mp4 批量转成 mp3。音频放在 audio_dir（默认与视频同目录）。"""
    Path(audio_dir).mkdir(parents=True, exist_ok=True)
    ffmpeg = ffmpeg_exe()
    count = 0
    for f in sorted(Path(video_dir).glob('*.mp4')):
        out = Path(audio_dir) / (f.stem + '.mp3')
        if out.exists():
            continue
        subprocess.run(
            [ffmpeg, '-y', '-i', str(f), '-vn',
             '-acodec', 'libmp3lame', '-q:a', '4', str(out)],
            check=False)
        print(f'剥音频: {f.name}')
        count += 1
    return count


def extract_one(video_file: str, audio_dir: str) -> Path:
    Path(audio_dir).mkdir(parents=True, exist_ok=True)
    ffmpeg = ffmpeg_exe()
    out = Path(audio_dir) / (Path(video_file).stem + '.mp3')
    subprocess.run(
        [ffmpeg, '-y', '-i', video_file, '-vn',
         '-acodec', 'libmp3lame', '-q:a', '4', str(out)],
        check=False)
    return out
