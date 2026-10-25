# vagent · 每日短视频 Agent

[English](README.md) · 中文

给一段中文文稿，在本地生成中文（视频号）和英文（X）两个竖屏成片，外加字幕、封面、发布文案和自动检查报告。**只在本地输出文件，从不上传或发布。**

## 需要什么

- macOS（安装脚本用 Homebrew；Apple 芯片或 Intel 均可）
- Python 3.11 及以上
- 已登录的 [Claude Code](https://claude.com/claude-code)（分镜、英文改写、发布文案都通过它完成，不需要 API key）
- 约 3 GB 硬盘空间（Kokoro 配音模型、Whisper 回听模型）

## 安装

```bash
git clone https://github.com/luzecheng/vagent.git
cd vagent
./install.sh                    # ffmpeg、Inter / Noto Sans CJK SC 字体、Python 环境、Kokoro 模型、Whisper、/make-video
./install.sh --with-cosyvoice   # 可选：CosyVoice 中文引擎（约 5 GB，很慢，见下文）
.venv/bin/vagent doctor         # 检查依赖
```

试一下：

```bash
.venv/bin/vagent run tests/fixtures/small_habits.txt
```

机器相关的设置写在 `.env`（不进版本库），例如 Claude 命令行需要走的代理：

```
VAGENT_CLAUDE_PROXY=http://127.0.0.1:7890
```

分镜与英文意译通过本机已登录的 Claude Code 命令行调用，不需要 API key。

## 使用

三种入口，做的事情完全一样（共用同一条流水线）：

### 1. Claude Code 里说一句

```
/make-video 把这篇做成视频：……（贴文稿）
```

Claude 会把文稿原样存到 `scripts/`，在后台运行，结束后用大白话告诉你 report.md 里需要注意什么。需要你决定的事情（例如稿件超长）它会先问你。

### 2. 收件箱（inbox）文件夹

```bash
vagent watch           # 一直开着：往 inbox/ 放 .txt / .md 文稿，自动出片（Ctrl+C 停止）
vagent watch --once    # 只处理现在 inbox 里的文稿，处理完退出
```

| 位置 | 含义 |
|---|---|
| `inbox/` | 把文稿放这里（文件名会成为输出文件夹名，中文可以） |
| `inbox/processing/` | 正在做的 |
| `inbox/done/` | 做完了，成片在 `output/YYYY-MM-DD_<文件名>/` |
| `inbox/paused/` | 需要你决定：看输出文件夹里的 `questions.md` |
| `inbox/failed/` | 出错了：原因在 `inbox/STATUS.md` 和输出文件夹的 `run.log.jsonl` |
| `inbox/STATUS.md` | 最近每篇文稿的结果和位置 |

每篇文稿在独立进程里做：一篇暂停或出错不影响其他文稿。还没写完（文件大小还在变）的文件会等下一轮再处理。

文稿开头可以写设置（没有命令行时用；命令行参数优先）：

```
---
allow_long: true     # 超过 140 秒也完整制作
landscape: true      # 另出英文 16:9 横屏版
disclaimer: on       # 强制加（off = 强制不加）免责声明
---
正文……
```

正文中单独一行 `---` 表示分集：每集各出一套成片，放在 `part1/`、`part2/` …

### 3. 命令行

```bash
vagent run script.txt                       # 文稿文件
vagent run --text "文稿内容"                 # 直接给文字
cat script.txt | vagent run -               # 从 stdin 读
vagent run script.txt --stage audio         # 只做配音 + 字幕（第 ① 阶段）
vagent run script.txt --allow-long          # 超过 140 秒也照常制作，不暂停
vagent run script.txt --disclaimer on|off   # 强制加 / 不加免责声明
vagent check output/<文件夹>                 # 对已有成片重新跑全部检查、重写 report.md（有必须处理的问题时退出码为 1）
vagent audition                             # 中文音色盲听样本
vagent doctor                               # 检查依赖、字体、模型、inbox、/make-video 是否就绪
```

结果在 `output/YYYY-MM-DD_<slug>/`：

| 文件 | 内容 |
|---|---|
| `zh_shipinhao.mp4` | 中文版，1080×1920，30fps，H.264 + AAC，中文字幕烧录 |
| `en_x_9x16.mp4` | 英文版，同规格，英文字幕烧录 |
| `en_x_16x9.mp4` | 可选（`--landscape` 或配置 `video.landscape_16x9: true`） |
| `zh.srt`、`en.srt` | 字幕文件 |
| `cover_zh.png`（3:4）、`cover_en.png`（9:16） | 封面。成片开头会先显示封面约 0.5 秒（平台默认用第一帧当缩略图），封面图也嵌在视频文件里当预览图；在 `config/default.yaml` 把 `video.cover_intro_s` 设为 0 可关闭片头封面 |
| `publish_notes.md` | 视频号标题（≤16 字）、简介、话题；X 推文（≤280，按 X 规则计数） |
| `script_zh_final.md`、`script_en_final.md`、`storyboard.json` | 终稿与分镜 |
| `report.md` | 制作报告：最上面是「需要你重点看的地方」（🔴 必须处理 / 🟡 请看一眼），其后是各项检查明细 |
| `contact_sheet_<版本>.png` | 关键帧总览：每个场景一帧，快速扫一眼画面 |
| `build/` | 中间文件：配音、时间轴、混音、回听检查等 |

需要你决定的事情（例如稿件超长）会写进 `questions.md`，任务暂停。**从不自动发布。**

### 画面与声音

- 分镜：Claude 从 15 个场景组件中为每句话挑选并填参数，经 schema 和语义校验（开头 3 秒钩子、每句恰好覆盖一次、不连用、数据红线），不通过自动重试。
- 免责声明：关键词规则 + 内容分类，投资 / 加密 / 理财类才在片尾显示 brand.yaml 里的免责文案并附在发布文案中；`--disclaimer on|off` 可强制。
- 混音：人声与成片响度 -16 LUFS。默认**不加背景音乐**；在 `config/default.yaml` 里把 `audio.music` 改成 `true` 可加回程序合成的背景音乐（每篇稿件调式不同，有人声时自动压低，首尾淡入淡出）。
- 字幕与文字全部在安全区内；视频号版本额外避开右侧与底部按钮区。超出画面区的场景会自动缩小字号。

### 自动检查（写进 report.md）

| 检查 | 内容 |
|---|---|
| 时长 | 目标 60–120 秒；英文超过 X 非会员上限 2:20 为 🔴，接近时 🟡；偏长时 Claude 给出删减建议（只建议，不改稿） |
| 规格 | 分辨率、30fps、H.264/yuv420p + AAC、音画轨等长 |
| 音画同步 | 每屏字幕都落在对应句子的发音时间内，首尾对齐，无重叠 |
| 安全区 | 画面文字、字幕、封面全部在安全区内；视频号版额外避开右侧和底部按钮 |
| 缺字 | 所有画面文字、字幕、封面逐字检查字体是否能显示（避免豆腐块） |
| 声音 | 成片响度 -16±1 LUFS、真峰值 ≤ -1 dBTP、无削波、配音中无超过 2 秒的静音 |
| 合规 | 规则扫描保证收益、价格预测、买卖指令、诱导话术；投资 / 加密类再由 Claude 逐句复核。只标出，不改原文 |
| 其他 | 中文口播微调清单、Whisper 回听可能读错的句子、免责声明判断理由、本次自动修正过的地方、分镜表 |

## 配置

四层，后者覆盖前者：`config/default.yaml` → `brand.yaml` → `config/local.yaml` → 命令行参数。

- `brand.yaml`：颜色、字体、水印、免责声明文案、音色、默认时长范围
- `config/default.yaml`：时长规则（目标 60–120 秒，硬上限 140 秒，最多加速 1.1 倍）、背景音乐开关、片头封面时长、停顿、字幕每行字数、LLM 设置
- `config/local.yaml`（可选，不进版本库）：只属于这台电脑的设置，例如改用 CosyVoice 音色

## 配音

每句单独合成再拼接，句间按标点留停顿；Kokoro 直接给出逐音素时长，所以中文每个字、英文每个词都有精确时间，字幕按真实时间切换。
每次配音后用 Whisper 把每句话转回文字和原稿比对（`build/asr_check.md`），自动标出可能读错、漏读的句子。

| 语言 | 默认 | 说明 |
|---|---|---|
| 英文 | Kokoro v1.0 · am_michael | 本地，约 2 秒合成一句 |
| 中文 | Kokoro v1.1-zh · zm_010 | 本地，约 1–2 秒合成一句 |
| 中文（可选） | CosyVoice-300M-SFT · 中文男 | 先 `./install.sh --with-cosyvoice`，再在 `config/local.yaml` 写 `tts: {zh: {provider: cosyvoice, model: cosyvoice-300m-sft, voice: "sft:中文男"}}`。必须跑在 CPU（Apple 芯片的 GPU 上会输出噪声 / 错字），2 分钟配音约 10 分钟，时间轴由 Whisper 对齐得到 |

换引擎：实现 `vagent.tts.base.Provider`（`synth()` 返回音频和逐字/逐词时间），在 `vagent/tts/__init__.py` 注册，然后在配置里改 `tts.zh.provider`。

## 缓存与日志

- 中间产物按内容哈希缓存在 `.cache/`：同一句话、同一音色、同一语速不会重复合成。
- 每次运行写 `run.log.jsonl`（结构化日志）；失败时日志最后一条给出错误和重试方法。重跑同一命令即可，已完成的部分直接复用缓存。

## 测试

```bash
.venv/bin/python -m pytest -q tests
```

## 许可证

[MIT](LICENSE)。配音模型（Kokoro、CosyVoice）、Whisper 和字体（Inter、Noto Sans CJK）由安装脚本从各自官方渠道下载，遵循各自的许可证，本仓库不包含它们。
