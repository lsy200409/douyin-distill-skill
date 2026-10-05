# 抖音蒸馏 Skill（v1）

把一个抖音账号的**公开作品**，批量变成能做决策的两样东西：

1. **一张能比较的表** —— 发布日期 / 时长 / 点赞 / 评论 / 收藏 / 标题，哪条真爆、哪条自嗨，一眼看出来；
2. **16 份文字稿** —— 人家到底怎么讲的、怎么起头、怎么收尾。

我拿它干过一件真事：**一个 16 条作品的账号，从抓链接到全部转写完成，35 分钟。**（12:44 开始 → 13:19 跑完，全程没开剪辑软件。）

---

## 它产出什么

| 目录 / 文件 | 内容 |
| --- | --- |
| `urls.txt` | 抓到的作品链接（一号一条） |
| `downloads/` | 每条作品的视频 + 音频（**仅本地学习用**） |
| `transcripts/` | 每条作品一份文字稿（faster-whisper 自动转写） |
| `meta-<备注>.jsonl` | 每条作品的公开数据（日期 / 时长 / 点赞 / 评论 / 收藏 / 分享） |
| `frames/` | 抽帧图（想看画面构图时用） |
| `cards/` | 蒸馏出的玩法卡（选题公式 / 钩子结构，需要自己填 LLM key） |

---

## 三步跑完（Python 3.10+）

```bash
pip install -r requirements.txt
cp config.sample.json config.json      # 填 douyin_home（对方主页链接）和备注名

python run.py login --config config.json         # 1. 扫码登录，cookie 存本地
python run.py scrape --config config.json        # 2. 抓主页作品链接 → urls.txt
python download_browser.py --config config.json  # 3. 下视频（浏览器态，最稳）
python run.py transcribe --config config.json    # 4. 全部转成文字稿
```

想要一条视频的最小闭环：`python run.py one --config config.json`

首次运行 `faster-whisper` 会下载模型（`small` 约 500MB）；没显卡用 `whisper_device: "cpu"`，慢但能跑。

---

## 三个真实踩过的坑

1. **未登录会弹登录框盖住主页**：抖音未登录态主页会弹「登录后免费畅享高清视频」，录屏/截图全被盖住 → 先 `run.py login`。
2. **部分视频下下来只有画面没有声音**：作品流里有纯视频的 DASH 分片。用 `download_audio_browser.py` 从 `aweme_detail.music.play_url` 单独补音轨。
3. **转写是增量的**：已经转过的会跳过，重复跑不会白等。

---

## 合规提醒（请务必读完再用）

- 只抓**公开可见**的数据；不要碰私信、不要碰需要授权的内容。
- 视频和音频**只留在本地做学习分析**，不要二次发布 —— 版权属于原作者。
- **蒸馏 = 学结构**（选题、节奏、钩子、命名、系列感），**不是抄内容**。抄别人的稿子发出去，是搬运。
- 遵守平台规则和当地法律。脚本作者不对使用者的行为负责。

---

## License

MIT，见 `LICENSE`。用得上就留着这段出处。
