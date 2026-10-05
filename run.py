"""抖音垂直博主批量蒸馏工具入口。

用法:
  python run.py one             # 最小闭环：只跑 1 条视频全链路
  python run.py all             # 批量：抓链接→下载→音频→转写→蒸馏
  python run.py stream          # 逐条流式：下载一条→转写→抽帧→删原视频→下一条（省磁盘）
  python run.py login           # 仅登录并导出 cookie
  python run.py scrape          # 仅抓博主主页链接生成 urls.txt
  python run.py download        # 仅批量下载
  python run.py audio           # 仅剥音频
  python run.py transcribe      # 仅转写
  python run.py frames          # 仅抽帧（供视觉提取画面内容）
  python run.py clean           # 仅删除原视频 mp4（转写/抽帧完成后省磁盘）
  python run.py distill         # 仅蒸馏玩法卡
"""
import argparse
import sys

from douyin import cookies as cookies_mod
from douyin import scrape as scrape_mod
from douyin import download as download_mod
from douyin import audio as audio_mod
from douyin import transcribe as transcribe_mod
from douyin import distill as distill_mod
from douyin import frames as frames_mod
from douyin import pipeline


def main():
    parser = argparse.ArgumentParser(description='抖音垂直博主批量蒸馏工具')
    parser.add_argument('cmd', choices=['one', 'all', 'stream', 'login', 'scrape', 'scrape_scroll',
                                        'download',
                                        'audio', 'transcribe', 'frames', 'clean', 'distill'])
    parser.add_argument('--config', default='config.json')
    args = parser.parse_args()

    cfg = pipeline.load_config(args.config)
    ck = cfg['cookies_file']

    if args.cmd == 'one':
        pipeline.run(args.config, one=True)
    elif args.cmd == 'all':
        pipeline.run(args.config, one=False)
    elif args.cmd == 'stream':
        pipeline.run_stream(args.config)
    elif args.cmd == 'login':
        cookies_mod.ensure_cookies(ck, force=True)
    elif args.cmd == 'scrape':
        home = cfg.get('douyin_home')
        if not home:
            sys.exit('请先在 config.json 填 douyin_home')
        scrape_mod.scrape_home_api(home, ck, cfg['urls_file'],
                                   max_videos=cfg.get('scrape_max_videos', 2000),
                                   headful=cfg.get('headful', False))
    elif args.cmd == 'scrape_scroll':
        home = cfg.get('douyin_home')
        if not home:
            sys.exit('请先在 config.json 填 douyin_home')
        scrape_mod.scrape_home(home, ck, cfg['urls_file'],
                               max_videos=cfg.get('scrape_max_videos', 2000),
                               headful=cfg.get('headful', True))
    elif args.cmd == 'download':
        download_mod.download_batch(cfg['urls_file'], ck, cfg['download_dir'])
    elif args.cmd == 'audio':
        audio_mod.extract_audio(cfg['download_dir'], cfg.get('audio_dir', cfg['download_dir']))
    elif args.cmd == 'transcribe':
        transcribe_mod.transcribe_all(cfg.get('audio_dir', cfg['download_dir']),
                                      cfg['transcript_dir'],
                                      cfg.get('whisper_model', 'small'),
                                      cfg.get('whisper_device', 'cuda'))
    elif args.cmd == 'frames':
        frames_mod.extract_frames(cfg['download_dir'],
                                  cfg.get('frames_dir', 'frames'),
                                  num_frames=cfg.get('num_frames', 8),
                                  max_frames=cfg.get('max_frames'))
    elif args.cmd == 'clean':
        deleted = pipeline.cleanup_videos(cfg['download_dir'],
                                          cfg.get('delete_videos', True))
        print(f'已删除 {deleted} 个 mp4 原视频。')
    elif args.cmd == 'distill':
        distill_mod.distill_all(cfg['transcript_dir'], cfg['llm'], cfg['cards_dir'],
                                blogger=cfg.get('blogger', ''))


if __name__ == '__main__':
    main()
