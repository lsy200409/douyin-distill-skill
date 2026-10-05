"""把口播稿经 LLM 蒸馏成「玩法卡」JSON，固定 schema + 结构化校验 + 失败重试。"""
import json
import os
import re
import time
from pathlib import Path

CARD_KEYS = ['index', 'source', 'title', 'hook', 'pain', 'play', 'selling', 'tag', 'reusable']

SYSTEM_PROMPT = (
    '你是一个短视频内容结构分析师。把博主的视频口播稿蒸馏成一张「玩法卡」，'
    '只输出合法的 JSON，不要输出任何多余文字、解释或 markdown 代码块。'
)


def _schema() -> dict:
    return {k: '' for k in CARD_KEYS}


def build_prompt(title: str, source: str, text: str) -> str:
    return (
        '下面是某博主的一期视频口播稿。请分析并输出一张玩法卡 JSON。\n\n'
        f'source: {source}\n'
        f'title: {title}\n'
        '口播稿:\n'
        f'{text}\n\n'
        '必须返回如下 JSON 结构（纯 JSON，不要 markdown 代码块）：\n'
        + json.dumps(_schema(), ensure_ascii=False, indent=2)
        + '\n\n字段说明：\n'
        '- index: 玩法卡编号（留空，由系统填）\n'
        '- source: 博主名/视频ID/时长（可留空）\n'
        '- title: 视频标题\n'
        '- hook: 前3秒钩子，怎么抓人\n'
        '- pain: 打的人群痛点\n'
        '- play: 核心玩法/可复用步骤，拆成几步，用中文分号(;)分隔\n'
        '- selling: 卖点/话术/转化点\n'
        '- tag: 归属垂类标签\n'
        '- reusable: 能否复用到手册的结论（是/否+一句话理由）\n'
    )


def call_llm(prompt: str, cfg: dict, retries: int = 3) -> dict:
    from openai import OpenAI
    client = OpenAI(base_url=cfg['base_url'], api_key=cfg['api_key'])
    last = None
    for i in range(retries):
        try:
            r = client.chat.completions.create(
                model=cfg['model'],
                messages=[
                    {'role': 'system', 'content': SYSTEM_PROMPT},
                    {'role': 'user', 'content': prompt},
                ],
                temperature=0.3,
            )
            text = (r.choices[0].message.content or '').strip()
            text = re.sub(r'^```(?:json)?\s*', '', text)
            text = re.sub(r'\s*```$', '', text)
            return json.loads(text)
        except Exception as e:
            last = e
            print(f'  蒸馏失败({i+1}/{retries}): {e}')
            time.sleep(2)
    raise RuntimeError(f'LLM 蒸馏失败: {last}')


def validate(data: dict) -> dict:
    for k in CARD_KEYS:
        if k not in data:
            data[k] = ''
    data['play'] = str(data.get('play', ''))
    return data


def next_index(cards_dir: str) -> str:
    n = len(list(Path(cards_dir).glob('玩-*.json'))) + 1
    return f'玩-{n:03d}'


def distill_one(transcript_file: str, cfg: dict, cards_dir: str,
                blogger: str = '', title: str = '') -> Path:
    Path(cards_dir).mkdir(parents=True, exist_ok=True)
    text = Path(transcript_file).read_text(encoding='utf-8')
    stem = Path(transcript_file).stem
    source = f'{blogger}/{stem}' if blogger else stem
    if not title:
        title = stem
    idx = next_index(cards_dir)
    prompt = build_prompt(title, source, text)
    data = call_llm(prompt, cfg)
    data['index'] = idx
    data['source'] = data.get('source') or source
    data['title'] = data.get('title') or title
    data = validate(data)
    out = Path(cards_dir) / f'{idx}.json'
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'玩法卡已生成: {out}')
    return out


def distill_all(transcript_dir: str, cfg: dict, cards_dir: str, blogger: str = '') -> int:
    files = sorted(Path(transcript_dir).glob('*.txt'))
    if not files:
        print(f'无口播稿可蒸馏: {transcript_dir}')
        return 0
    count = 0
    for f in files:
        print(f'蒸馏: {f.name}')
        distill_one(str(f), cfg, cards_dir, blogger=blogger)
        count += 1
    return count
