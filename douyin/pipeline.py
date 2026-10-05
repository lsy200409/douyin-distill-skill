"""一键流水线编排：cookies → 抓链接 → 下载 → 剥音频 → 转写 → 蒸馏。

支持 --one 模式：只跑 1 条视频的完整最小闭环，用于先验证工具能出料。
"""
import json
import os
from pathlib import Path

from . import cookies as cookies_mod
from . import scrape as scrape_mod
from . import download as download_mod
from . import audio as audio_mod
from . import transcribe as transcribe_mod
from . import frames as frames_mod
from . import distill as distill_mod


def load_config(path: str = 'config.json') -> dict:
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _llm_ready(cfg: dict) -> bool:
    return bool(cfg.get('llm', {}).get('api_key'))


def _first_url(urls_file: str) -> str:
    lines = [l.strip() for l in Path(urls_file).read_text(encoding='utf-8').splitlines() if l.strip()]
    return lines[0] if lines else ''


def cleanup_videos(download_dir: str, delete: bool = True) -> int:
    """转写+抽帧完成后删除原视频 mp4，只留 mp3/txt/frames 以节省磁盘。"""
    if not delete:
        return 0
    n = 0
    for f in sorted(Path(download_dir).glob('*.mp4')):
        try:
            f.unlink()
            n += 1
        except OSError as e:
            print(f'删除失败 {f.name}: {e}')
    return n


def run(config_path: str = 'config.json', one: bool = False) -> None:
    cfg = load_config(config_path)
    urls_file = cfg['urls_file']
    cookies_file = cfg['cookies_file']
    download_dir = cfg['download_dir']
    audio_dir = cfg.get('audio_dir', download_dir)
    transcript_dir = cfg['transcript_dir']
    cards_dir = cfg['cards_dir']
    blogger = cfg.get('blogger', '')
    whisper_model = cfg.get('whisper_model', 'small')
    whisper_device = cfg.get('whisper_device', 'cuda')
    headful = cfg.get('headful', True)

    # 1) cookie
    cookies_mod.ensure_cookies(cookies_file)

    # 2) 链接清单（one 模式直接取第一条；否则若 urls.txt 缺失则抓主页）
    if one:
        if not os.path.exists(urls_file):
            raise SystemExit(f'--one 模式需要先有 {urls_file}，请先运行抓链接或手动填 url。')
        url = _first_url(urls_file)
        if not url:
            raise SystemExit(f'{urls_file} 为空。')
        print(f'[最小闭环] 处理 1 条: {url}')
        download_mod.download_one(url, cookies_file, download_dir)
        # 找到刚下载的 mp4
        vids = sorted(Path(download_dir).glob('*.mp4'))
        if not vids:
            raise SystemExit('下载失败，未得到 mp4。')
        video_file = str(vids[-1])
        print(f'[下载完成] {video_file}')

        # 剥音频
        mp3 = audio_mod.extract_one(video_file, audio_dir)
        print(f'[音频] {mp3}')

        # 转写
        transcript_mod.transcribe_one(str(mp3), transcript_dir, whisper_model, whisper_device)
        txt = Path(transcript_dir) / (Path(mp3).stem + '.txt')
        print(f'[转写] {txt}')

        # 抽帧（供视觉提取画面内容）
        frames_dir = cfg.get('frames_dir', 'frames')
        frames_mod.extract_frames(download_dir, frames_dir,
                                  num_frames=cfg.get('num_frames', 8),
                                  max_frames=cfg.get('max_frames'))
        print(f'[抽帧] 输出目录: {frames_dir}')

        # 转写+抽帧完成后删原视频，省磁盘
        deleted = cleanup_videos(download_dir, cfg.get('delete_videos', True))
        if deleted:
            print(f'[清理] 删除 {deleted} 个原视频 mp4')

        # 蒸馏
        if not _llm_ready(cfg):
            print('警告: config.json 未配置 llm.api_key，跳过蒸馏。')
            return
        distill_mod.distill_one(str(txt), cfg['llm'], cards_dir, blogger=blogger)
        return

    # 批量模式
    if not os.path.exists(urls_file):
        home = cfg.get('douyin_home')
        if not home:
            raise SystemExit(f'缺少 {urls_file}，且 config.json 未配置 douyin_home。请填主页或手动建 urls.txt。')
        print('抓取博主主页视频链接…')
        scrape_mod.scrape_home(home, cookies_file, urls_file,
                               max_videos=cfg.get('scrape_max_videos', 50),
                               headful=headful)

    download_mod.download_batch(urls_file, cookies_file, download_dir)
    audio_mod.extract_audio(download_dir, audio_dir)
    transcribe_mod.transcribe_all(audio_dir, transcript_dir, whisper_model, whisper_device)
    frames_mod.extract_frames(download_dir, cfg.get('frames_dir', 'frames'),
                              num_frames=cfg.get('num_frames', 8),
                              max_frames=cfg.get('max_frames'))
    # 转写+抽帧完成后删原视频，省磁盘
    deleted = cleanup_videos(download_dir, cfg.get('delete_videos', True))
    if deleted:
        print(f'[清理] 删除 {deleted} 个原视频 mp4')
    if not _llm_ready(cfg):
        print('警告: config.json 未配置 llm.api_key，跳过蒸馏。')
        return
    distill_mod.distill_all(transcript_dir, cfg['llm'], cards_dir, blogger=blogger)


def _process_one(video_file: str, cfg: dict, model, audio_dir, transcript_dir,
                 frames_dir) -> bool:
    """对单个 mp4：剥音频→转写→抽帧→删原视频。返回是否处理过。"""
    v = Path(video_file)
    if v.suffix != '.mp4' or not v.exists():
        return False
    # 若已有转写稿且已抽帧，说明已完成，仅删原视频
    txt = Path(transcript_dir) / (v.stem + '.txt')
    if txt.exists():
        frames_mod.extract_frames_one(str(v), frames_dir, cfg.get('num_frames', 8))
        audio_mod.extract_one(str(v), audio_dir)
        v.unlink(missing_ok=True)
        print(f'[已完成] 删除原视频: {v.name}')
        return True
    # 剥音频
    mp3 = audio_mod.extract_one(str(v), audio_dir)
    print(f'[音频] {mp3.name}')
    # 转写（复用模型）
    out = transcribe_mod.transcribe_one_reuse(model, str(mp3), transcript_dir)
    print(f'[转写] {out.name}')
    # 抽帧
    frames_mod.extract_frames_one(str(v), frames_dir, cfg.get('num_frames', 8))
    # 删原视频省磁盘
    if cfg.get('delete_videos', True):
        v.unlink(missing_ok=True)
        print(f'[清理] 删除原视频: {v.name}')
    return True


def run_stream(config_path: str = 'config.json') -> None:
    """逐条流式：下载单条→剥音频→转写→抽帧→删原视频，省磁盘、出料及时。
    先补齐存量未处理 mp4，再遍历 urls.txt 下载剩余视频逐条处理。"""
    cfg = load_config(config_path)
    urls_file = cfg['urls_file']
    cookies_file = cfg['cookies_file']
    download_dir = cfg['download_dir']
    audio_dir = cfg.get('audio_dir', download_dir)
    transcript_dir = cfg['transcript_dir']
    frames_dir = cfg.get('frames_dir', 'frames')
    whisper_model = cfg.get('whisper_model', 'small')
    whisper_device = cfg.get('whisper_device', 'cuda')

    # 复用同一个模型，避免每条都重新加载
    model = transcribe_mod._load_model(whisper_model, whisper_device)

    # 1) 补齐存量：downloads 里未转写的 mp4 立即处理
    for v in sorted(Path(download_dir).glob('*.mp4')):
        _process_one(str(v), cfg, model, audio_dir, transcript_dir, frames_dir)

    # 2) 遍历 urls.txt 下载剩余并逐条处理
    if not os.path.exists(urls_file):
        print(f'无 {urls_file}，仅处理存量。')
        return
    urls = [l.strip() for l in Path(urls_file).read_text(encoding='utf-8').splitlines() if l.strip()]
    # 已转写的视频 ID 集合（从转写稿文件名尾部 .视频ID.txt 提取），用于跳过无需重新下载的
    import re as _re
    done_ids = set()
    for t in Path(transcript_dir).glob('*.txt'):
        m = _re.search(r'\.(\d{15,25})\.txt$', t.name)
        if m:
            done_ids.add(m.group(1))
    print(f'共 {len(urls)} 条链接，已转写 {len(done_ids)} 条，开始逐条流式处理…')
    for url in urls:
        # 从 URL 提取视频 ID，若已转写则跳过下载
        um = _re.search(r'/video/(\d{15,25})', url)
        if um and um.group(1) in done_ids:
            print(f'跳过已转写: {url}')
            continue
        # 记录下载前已有的 mp4，便于精确定位本条新增产物
        before = {p.stem for p in Path(download_dir).glob('*.mp4')}
        download_mod.download_one(url, cookies_file, download_dir)
        # 找到本条新增的 mp4（按 stem 取不在 before 中的）
        new_vids = [p for p in Path(download_dir).glob('*.mp4') if p.stem not in before]
        if not new_vids:
            print(f'跳过（无新增产物）: {url}')
            continue
        _process_one(str(new_vids[0]), cfg, model, audio_dir, transcript_dir, frames_dir)
    print('流式处理完成。')

