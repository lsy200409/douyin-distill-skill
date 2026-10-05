"""快速画像：从 meta-编导.jsonl 输出选题/数据表。"""
import json
import statistics as st

rows = [json.loads(l) for l in open('meta-编导.jsonl', encoding='utf-8') if l.strip()]
seen = {}
for r in rows:
    seen[r['aweme_id']] = r
rows = sorted(seen.values(), key=lambda r: r['date'])

print('账号:', rows[0].get('author'))
print('作品数:', len(rows))
hdr = f"{'日期':<16}{'时长':>6}{'赞':>7}{'评':>6}{'藏':>7}{'转':>6}{'藏/赞':>7}{'评/赞':>7}  标题"
print(hdr)
for r in rows:
    d = r['digg'] or 0
    c = r['comment'] or 0
    col = r['collect'] or 0
    s = r['share'] or 0
    f = (lambda x: x / d if d else 0)
    print(f"{r['date']:<16}{r['duration_s']:>6.0f}{d:>7}{c:>6}{col:>7}{s:>6}{f(col):>7.2f}{f(c):>7.2f}  {r['desc'][:46]}")

ds = [r['duration_s'] for r in rows]
dg = [r['digg'] or 0 for r in rows]
print()
print('时长 中位 %.0fs 最短 %.0fs 最长 %.0fs' % (st.median(ds), min(ds), max(ds)))
print('点赞 中位 %d 最高 %d 最低 %d' % (st.median(dg), max(dg), min(dg)))
print('总时长 %.1f 分钟' % (sum(ds) / 60))
