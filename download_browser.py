"""浏览器态下载器 v2：Playwright 打开抖音视频页 → 截获 aweme/detail 元数据 → 从 detail 里挑**带视频流的**清晰度直链下载。

为什么需要 v2：v1 只按 URL 关键字抓第一个 douyinvod 直链，结果一部分拿到的是**纯音频流**
（下载下来的 "mp4" 用 ffprobe 看只有 aac 音频轨、没有视频轨），抽帧全失败。
v2 改为优先用 `aweme_detail.video.play_addr / bit_rate[]` 的清晰度列表，并在保存前用 av 校验存在视频轨。

用法:
  python download_browser.py --urls urls-编导.txt --out downloads-bd --meta meta-编导.jsonl [--limit N]
  python download_browser.py --verify-only --out downloads-bd      # 只检查已下载文件有没有视频轨
"""
import argparse
import json
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

from douyin.cookies import ensure_cookies, UA
from douyin.scrape import _load_cookies_into_context

SKIP_EXT = ('.jpg', '.jpeg', '.png', '.webp', '.gif')


def has_video_stream(path) -> bool:
    try:
        import av
        with av.open(str(path)) as c:
            return any(s.type == 'video' for s in c.streams)
    except Exception:
        return False


def detail_candidates(ad: dict):
    """从 aweme_detail 里按清晰度升序给出 (url, 描述) 候选。"""
    out = []
    v = ad.get('video') or {}
    for br in (v.get('bit_rate') or []):
        pa = br.get('play_addr') or {}
        for u in (pa.get('url_list') or []):
            if u.startswith('http'):
                h = pa.get('height') or 0
                out.append((h, br.get('gear_name', ''), u))
    # 兜底：默认播放地址（带水印但一定有视频轨）
    for key in ('play_addr', 'download_addr'):
        pa = v.get(key) or {}
        for u in (pa.get('url_list') or []):
            if u.startswith('http'):
                out.append((pa.get('height') or 0, key, u))
    out.sort(key=lambda x: (x[0] if x[0] else 9999))
    return out


def download_one(ctx, url, out_dir: Path, meta_path: Path, idx: int, total: int):
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
    aweme_id = ad.get('aweme_id') or url.rstrip('/').split('/')[-1].split('?')[0]
    desc = ad.get('desc') or ''
    create_time = ad.get('create_time')
    duration = ((ad.get('video') or {}).get('duration') or 0) / 1000.0
    st = ad.get('statistics') or {}
    author = (ad.get('author') or {}).get('nickname') or ''

    cands = [(h, g, u) for (h, g, u) in detail_candidates(ad)]
    # 截获到的、content-type 明确是视频的直链，排在最前
    for u, ct in media:
        if ct.startswith('video') and u.lower().split('?')[0].endswith(SKIP_EXT) is False:
            cands.insert(0, (0, 'intercepted:' + ct, u))

    rec = {
        'aweme_id': aweme_id, 'url': url, 'desc': desc, 'author': author,
        'create_time': create_time,
        'date': time.strftime('%Y-%m-%d %H:%M', time.localtime(create_time)) if create_time else '',
        'duration_s': round(duration, 1),
        'digg': st.get('digg_count'), 'comment': st.get('comment_count'),
        'collect': st.get('collect_count'), 'share': st.get('share_count'),
        'candidates': len(cands),
    }

    tmp = out_dir / f'{aweme_id}.part'
    saved = None
    tried = 0
    for h, gear, u in cands[:8]:
        tried += 1
        try:
            r = requests.get(u, headers={'User-Agent': UA, 'Referer': 'https://www.douyin.com/'},
                             timeout=120, stream=True)
            if r.status_code != 200:
                continue
            with tmp.open('wb') as f:
                for chunk in r.iter_content(1 << 16):
                    f.write(chunk)
            if tmp.stat().st_size > 50_000 and has_video_stream(tmp):
                fp = out_dir / f'{aweme_id}.mp4'
                tmp.replace(fp)
                saved = fp
                rec.update({'file': fp.name, 'bytes': fp.stat().st_size, 'gear': gear, 'height': h})
                break
        except Exception as e:
            rec.setdefault('errors', []).append(f'{gear}: {type(e).__name__}')
    if tmp.exists():
        tmp.unlink()
    if not saved:
        rec['download_error'] = f'{tried} 个候选都没有视频轨'

    with meta_path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    print(f'[{idx}/{total}] {aweme_id} | {rec["date"]} | {rec["duration_s"]}s | 赞{rec["digg"]} | '
          f'{"OK " + str(rec.get("bytes", 0) // 1024) + "KB @" + str(rec.get("height")) + "p" if saved else "FAIL " + str(rec.get("download_error"))}'
          f' | {desc[:36]}', flush=True)
    page.close()
    return bool(saved)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--urls', default='urls-编导.txt')
    ap.add_argument('--cookies', default='cookies.txt')
    ap.add_argument('--out', default='downloads-bd')
    ap.add_argument('--meta', default='meta-编导.jsonl')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--headful', action='store_true')
    ap.add_argument('--verify-only', action='store_true')
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.verify_only:
        bad = []
        for f in sorted(out_dir.glob('*.mp4')):
            ok = has_video_stream(f)
            if not ok:
                bad.append(f)
                print(f'✗ 无视频轨 {f.name} ({f.stat().st_size // 1024}KB)')
        print(f'检查完成：{len(list(out_dir.glob("*.mp4")))} 个文件，{len(bad)} 个无视频轨')
        return

    ensure_cookies(args.cookies)
    urls = [l.strip() for l in Path(args.urls).read_text(encoding='utf-8').splitlines() if l.strip()]
    if args.limit:
        urls = urls[:args.limit]
    meta_path = Path(args.meta)

    ok = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headful)
        ctx = browser.new_context(locale='zh-CN', user_agent=UA)
        _load_cookies_into_context(ctx, args.cookies)
        for i, u in enumerate(urls, 1):
            vid = u.rstrip('/').split('/')[-1].split('?')[0]
            fp = out_dir / f'{vid}.mp4'
            if fp.exists() and has_video_stream(fp):
                print(f'[{i}/{len(urls)}] {vid} 已有视频轨，跳过', flush=True)
                ok += 1
                continue
            if fp.exists():
                print(f'[{i}/{len(urls)}] {vid} 旧文件无视频轨，重下', flush=True)
                fp.unlink()
            try:
                if download_one(ctx, u, out_dir, meta_path, i, len(urls)):
                    ok += 1
            except Exception as e:
                print(f'[{i}/{len(urls)}] 异常 {type(e).__name__}: {e}', flush=True)
        browser.close()
    print(f'完成：成功 {ok}/{len(urls)}', flush=True)


if __name__ == '__main__':
    main()
