"""把转写稿压成"可快速通读"的形态：每条给 钩子(前 150 字) / 收口(后 120 字) / 字数 / 句数 / 高频结构词。

用法: python brief_transcripts.py [--full <aweme_id>]
"""
import argparse
import json
import re
from pathlib import Path

BASE = Path('.')


def load_meta():
    m = {}
    for l in Path('meta-编导.jsonl').read_text(encoding='utf-8').splitlines():
        if l.strip():
            r = json.loads(l)
            m[r['aweme_id']] = r
    return m


def split_sents(t):
    return [s for s in re.split(r'[。！？!?]', t) if s.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--full', default='')
    ap.add_argument('--top', type=int, default=0)
    args = ap.parse_args()

    meta = load_meta()
    files = sorted(Path('transcripts-bd').glob('*.txt'))
    if args.full:
        f = Path('transcripts-bd') / f'{args.full}.txt'
        t = f.read_text(encoding='utf-8').strip()
        r = meta.get(args.full, {})
        print(f"### {args.full} | {r.get('date','')} | {r.get('duration_s',0):.0f}s | 赞{r.get('digg')} | {r.get('desc','')}")
        print(t)
        return

    rows = []
    for f in files:
        vid = f.stem
        t = f.read_text(encoding='utf-8').strip()
        r = meta.get(vid, {})
        sents = split_sents(t)
        rows.append((vid, r, t, sents))

    rows.sort(key=lambda x: -(x[1].get('digg') or 0))
    if args.top:
        rows = rows[:args.top]

    for vid, r, t, sents in rows:
        d = r.get('digg') or 0
        col = r.get('collect') or 0
        print(f"\n=== {vid} | {r.get('date','')} | {r.get('duration_s',0):.0f}s | 赞{d} 藏{col} | 字数{len(t)} 句{len(sents)}")
        print(f"    标题: {r.get('desc','')}")
        print(f"    钩子: {t[:160]}")
        print(f"    收口: {t[-130:]}")


if __name__ == '__main__':
    main()
