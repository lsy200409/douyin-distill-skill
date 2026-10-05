"""浏览器态**音频**下载器：给已下过视频但**没有音频轨**的那些 aweme_id 补音频（用于口播转写）。

为什么需要：`download_browser.py` v2 为了保证"有视频轨"，可能选中 DASH 的**纯视频**分片
（结果那几个 mp4 只有 h264、没有 aac，ffmpeg 剥音频报 "Output file does not contain any stream"）。
本脚本改为只找**音频**：截获视频页所有 douyinvod 响应 + detail JSON 里的 `music.play_url`
（原声视频的 music 就是这个视频的混合音轨），逐个试到能解出音频轨为止，存成 mp3。

用法:
  python download_audio_browser.py --ids 7661193344018867697,7661895150721534641 --out downloads-bd [--headful]
"""
import argparse
import json
import subprocess
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

from douyin.cookies import ensure_cookies, UA
from douyin.scrape import _load_cookies_into_context

FFMPEG = (r'C:\Users\28845\AppData\Local\Microsoft\WinGet\Packages'
          r'\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe'
          r'\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe')


def has_audio_stream(path) -> bool:
    try:
        import av
        with av.open(str(path)) as c:
            return any(s.type == 'audio' for s in c.streams)
    except Exception:
        return False


def to_mp3(src: Path, dst: Path) -> bool:
    r = subprocess.run([FFMPEG, '-v', 'error', '-i', str(src), '-vn', '-ac', '1',
                        '-ar', '16000', '-b:a', '64k', '-y', str(dst)],
                       capture_output=True)
    return dst.exists() and r.returncode == 0


def fetch_audio(ctx, aweme_id: str, out_dir: Path) -> bool:
    url = f'https://www.douyin.com/video/{aweme_id}'
    page = ctx.new_page()
    page.set_default_timeout(60000)
    media, detail = [], {}

    def on_response(resp):
        u = resp.url
        try:
            if '/aweme/v1/web/aweme/detail/' in u and resp.status == 200:
                detail.update(resp.json())
            elif 'douyinvod.com' in u or '/aweme/v1/play/' in u:
                ct = (resp.headers or {}).get('content-type', '')
                if u not in [m[0] for m in media]:
                    media.append((u, ct))
        except Exception:
            pass

    page.on('response', on_response)
    page.goto(url, wait_until='domcontentloaded', timeout=90000)
    page.wait_for_timeout(6000)
    ad = detail.get('aweme_detail') or {}

    cands = []
    # 1) 截获到的音频型响应
    for u, ct in media:
        if ct.startswith('audio') or 'audio' in ct:
            cands.append((u, 'intercepted:' + ct))
    # 2) 原声（原声视频的 music 就是这个视频的音轨）
    for key in ('music',):
        for u in (((ad.get(key) or {}).get('play_url') or {}).get('url_list') or []):
            if u.startswith('http'):
                cands.append((u, key))
    # 3) 兜底：所有截获链接
    for u, ct in media:
        cands.append((u, 'any:' + ct))

    tmp = out_dir / f'{aweme_id}.part'
    ok = False
    for u, tag in cands[:10]:
        try:
            r = requests.get(u, headers={'User-Agent': UA, 'Referer': 'https://www.douyin.com/'},
                             timeout=120, stream=True)
            if r.status_code != 200:
                continue
            with tmp.open('wb') as f:
                for chunk in r.iter_content(1 << 16):
                    f.write(chunk)
            if tmp.stat().st_size > 10_000 and has_audio_stream(tmp):
                mp3 = out_dir / f'{aweme_id}.mp3'
                if to_mp3(tmp, mp3):
                    ok = True
                    print(f'  ✓ {aweme_id} 音频 {mp3.stat().st_size // 1024}KB（来源 {tag}）', flush=True)
                    break
        except Exception as e:
            print(f'  · 候选失败 {tag}: {type(e).__name__}', flush=True)
    if tmp.exists():
        tmp.unlink()
    if not ok:
        print(f'  ✗ {aweme_id} 没有找到可用音频（试了 {len(cands[:10])} 个候选）', flush=True)
    page.close()
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ids', required=True, help='逗号分隔的 aweme_id')
    ap.add_argument('--cookies', default='cookies.txt')
    ap.add_argument('--out', default='downloads-bd')
    ap.add_argument('--headful', action='store_true')
    args = ap.parse_args()

    out_dir = Path(args.out)
    ids = [i.strip() for i in args.ids.split(',') if i.strip()]
    ensure_cookies(args.cookies)
    ok = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headful)
        ctx = browser.new_context(locale='zh-CN', user_agent=UA)
        _load_cookies_into_context(ctx, args.cookies)
        for vid in ids:
            if (out_dir / f'{vid}.mp3').exists():
                print(f'{vid} 已有 mp3，跳过', flush=True)
                ok += 1
                continue
            print(f'[{ids.index(vid) + 1}/{len(ids)}] {vid}', flush=True)
            try:
                if fetch_audio(ctx, vid, out_dir):
                    ok += 1
            except Exception as e:
                print(f'  异常 {type(e).__name__}: {e}', flush=True)
        browser.close()
    print(f'完成：{ok}/{len(ids)}')


if __name__ == '__main__':
    main()
