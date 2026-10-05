"""录制真实浏览器操作素材（不经剪辑的原始录屏）：打开博主主页 → 滚动看作品 → 存 webm。

用法:
  python record_home.py --config config-编导.json --out ..\\..\\work\\素材录屏\\主页滚动 --seconds 30
"""
import argparse
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

from douyin.cookies import ensure_cookies, UA
from douyin.scrape import _load_cookies_into_context


async def run(args):
    cfg = json.loads(Path(args.config).read_text(encoding='utf-8'))
    ck = cfg['cookies_file']
    home = cfg['douyin_home']
    ensure_cookies(ck)

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        ctx = await browser.new_context(
            locale='zh-CN',
            user_agent=UA,
            viewport={'width': 720, 'height': 1280},
            record_video_dir=str(outdir),
            record_video_size={'width': 720, 'height': 1280},
        )
        _load_cookies_into_context(ctx, ck)
        page = await ctx.new_page()
        print('打开主页…')
        await page.goto(home, wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_timeout(4000)
        # 关掉登录弹窗（否则整段录屏被"登录后免费畅享高清视频"盖住）
        await page.keyboard.press('Escape')
        removed = await page.evaluate(
            """() => {
                const hits = [...document.querySelectorAll('div')].filter((d) => {
                    const s = getComputedStyle(d);
                    return s.position === 'fixed' && parseInt(s.zIndex || 0) > 100
                        && d.innerText && d.innerText.includes('登录');
                });
                hits.forEach((d) => d.remove());
                return hits.length;
            }"""
        )
        print(f'关掉登录弹窗: {removed} 个')
        await page.wait_for_timeout(1200)
        steps = max(4, args.seconds // 2)
        for i in range(steps):
            await page.mouse.wheel(0, 700)
            await page.wait_for_timeout(1400)
            print(f'  滚动 {i + 1}/{steps}')
        await page.wait_for_timeout(1500)
        await ctx.close()
        await browser.close()

    vids = sorted(outdir.glob('*.webm'), key=lambda f: f.stat().st_mtime)
    print('录制完成:', vids[-1] if vids else '无')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', default='config-编导.json')
    ap.add_argument('--out', default='素材录屏')
    ap.add_argument('--seconds', type=int, default=30)
    args = ap.parse_args()
    asyncio.run(run(args))


if __name__ == '__main__':
    main()
