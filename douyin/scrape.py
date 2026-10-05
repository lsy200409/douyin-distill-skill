"""博主主页自动滚动，抓取全部 www.douyin.com/video/xxx 链接生成 urls.txt。"""
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

from .cookies import ensure_cookies, UA

VIDEO_PAT = '/video/'


def _load_cookies_into_context(ctx, cookies_file: str):
    """把 Netscape cookie jar 手动解析后注入 playwright context（绕开 cookiejar bug）。"""
    if not os.path.exists(cookies_file):
        return
    added = 0
    for line in Path(cookies_file).read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split('\t')
        if len(parts) < 7:
            continue
        domain, _sub, path, _sec, _exp, name, value = parts[:7]
        if not domain:
            continue
        try:
            ctx.add_cookies([{
                'name': name,
                'value': value,
                'domain': domain,
                'path': path or '/',
                'secure': parts[3] == 'TRUE',
                'expires': int(parts[4]) if parts[4].isdigit() and int(parts[4]) > 0 else -1,
            }])
            added += 1
        except Exception:
            pass
    print(f'已注入 {added} 条 cookie')


def scrape_home(home_url: str, cookies_file: str, out_urls: str,
                max_videos: int = 50, headful: bool = True) -> int:
    ensure_cookies(cookies_file)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headful)
        ctx = browser.new_context(locale='zh-CN', user_agent=UA)
        _load_cookies_into_context(ctx, cookies_file)
        page = ctx.new_page()
        page.set_default_timeout(60000)
        page.goto(home_url, wait_until='domcontentloaded', timeout=90000)
        page.wait_for_timeout(8000)

        found = set()
        stall = 0
        # 首次加载等待视频链接出现（异步渲染），避免一上来就误判到底
        for _ in range(40):
            hrefs = page.eval_on_selector_all(
                'a[href*="/video/"]', 'els => els.map(e => e.href)')
            if any(VIDEO_PAT in h for h in hrefs):
                for h in hrefs:
                    h = h.split('?')[0]
                    if VIDEO_PAT in h:
                        found.add(h)
                break
            page.mouse.wheel(0, 1800)
            page.wait_for_timeout(900)
        else:
            print('等待视频链接超时（可能需登录或页面异常）。')
        # 持续滚动到底：以“页面高度是否继续增长”为到底判据，容忍更久
        last_height = page.evaluate('document.body.scrollHeight')
        height_stall = 0
        for _ in range(2000):
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(900)
            hrefs = page.eval_on_selector_all(
                'a[href*="/video/"]', 'els => els.map(e => e.href)')
            before = len(found)
            for h in hrefs:
                h = h.split('?')[0]  # 去掉 ?source= 等查询参数，只留干净视频链接
                if VIDEO_PAT in h:
                    found.add(h)
            if len(found) >= max_videos:
                print(f'已达目标上限 {max_videos}，停止滚动。')
                break
            # 页面高度不再增长 → 判定到底
            cur = page.evaluate('document.body.scrollHeight')
            if cur <= last_height:
                height_stall += 1
            else:
                height_stall = 0
                last_height = cur
            if height_stall >= 15:
                print('滚动到底，页面高度不再增长。')
                break
        browser.close()

    lines = sorted(found)
    Path(out_urls).write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'抓取到 {len(lines)} 个视频链接 -> {out_urls}')
    return len(lines)


def scrape_home_api(home_url: str, cookies_file: str, out_urls: str,
                    max_videos: int = 2000, headful: bool = False) -> int:
    """滚动主页 + 监听 aweme/post 网络响应，收集全部视频链接。
    页面自己滚动并携带合法签名，我们只从响应里捞 aweme_list，稳定拿到全量。"""
    import re
    import sys
    import json as _json
    ensure_cookies(cookies_file)
    m = re.search(r'/user/([A-Za-z0-9_-]+)', home_url)
    if not m:
        raise SystemExit(f'无法从主页 URL 提取 sec_user_id: {home_url}')
    sec_uid = m.group(1)

    def dump(found):
        Path(out_urls).write_text('\n'.join(sorted(found)) + '\n', encoding='utf-8')

    found = set()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headful)
        ctx = browser.new_context(locale='zh-CN', user_agent=UA)
        _load_cookies_into_context(ctx, cookies_file)
        page = ctx.new_page()
        page.set_default_timeout(60000)

        # 监听 aweme/post 接口响应，收集视频 ID
        def on_response(resp):
            try:
                if '/aweme/v1/web/aweme/post/' in resp.url:
                    if resp.status != 200:
                        print(f'post接口状态 {resp.status}', flush=True)
                        return
                    data = resp.json()
                    n = 0
                    for a in (data.get('aweme_list') or []):
                        vid = a.get('aweme_id')
                        if vid:
                            found.add(f'https://www.douyin.com/video/{vid}')
                            n += 1
                    print(f'post响应 +{n} 累计 {len(found)}', flush=True)
                    dump(found)
            except Exception as e:
                print(f'解析post响应失败: {e}', flush=True)
        page.on('response', on_response)

        page.goto('https://www.douyin.com/user/' + sec_uid, wait_until='domcontentloaded', timeout=90000)
        page.wait_for_timeout(5000)

        # 持续滚动触发加载（多滚固定次数，瀑布流可能高度不变但继续加载）
        for _ in range(500):
            page.mouse.wheel(0, 3000)
            page.wait_for_timeout(1500)
            if len(found) >= max_videos:
                print(f'已达上限 {max_videos}，停止。', flush=True)
                break
        print(f'滚动结束，累计 {len(found)} 条', flush=True)
        browser.close()

    lines = sorted(found)
    Path(out_urls).write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'API 抓取到 {len(lines)} 个视频链接 -> {out_urls}')
    return len(lines)
