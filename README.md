# 中文法律案例短视频生产执行器（V1）

本项目是一个**本地命令行执行器**，用于将单个中文法律案例文档转成短视频生产物料（脚本、配音稿、字幕、镜头清单），并预留后续接入图片生成、TTS、FFmpeg 合成能力。

## 目标范围（V1）
- ✅ 本地运行
- ✅ 命令行入口
- ✅ 基于 mock provider 跑通全链路
- ✅ 可切换真实 LLM provider（OpenAI 兼容）
- ✅ 可切换本地 TTS provider
- ✅ 可切换 FFmpeg provider 输出 `final.mp4`
- ✅ 所有输出落盘，可重跑、可复用
- ❌ 不做前端页面
- ❌ 不做数据库/用户系统

## 目录结构

```text
cases/                  输入案例
output/                 执行输出
assets/                 资源占位
app/
  main.py
  config.py
  models.py
  pipeline.py
  provider_factory.py
  providers/
    llm_provider.py
    image_provider.py
    tts_provider.py
    video_provider.py
  steps/
    parse_case.py
    generate_materials.py
    render_images.py
    render_audio.py
    render_video.py
scripts/
  run_case.py
tests/
```

## 环境要求
- Python 3.10+
- UTF-8 编码
- 可选：
  - 本地 TTS：`pip install pyttsx3`
  - 视频合成：安装 `ffmpeg` 并加入 PATH

## 快速开始

### 1) 默认（全 mock）

```bash
python scripts/run_case.py --case cases/case_001.md
```

### 2) 使用真实 LLM（OpenAI 兼容接口）

```bash
# Linux/macOS
export LCT_LLM_PROVIDER=openai_compatible
export LCT_LLM_BASE_URL=http://127.0.0.1:8000/v1
export LCT_LLM_MODEL=qwen2.5:7b-instruct
python scripts/run_case.py --case cases/case_001.md --fallback-to-mock
```

```powershell
# Windows PowerShell
$env:LCT_LLM_PROVIDER="openai_compatible"
$env:LCT_LLM_BASE_URL="http://127.0.0.1:8000/v1"
$env:LCT_LLM_MODEL="qwen2.5:7b-instruct"
python scripts/run_case.py --case cases/case_001.md --fallback-to-mock
```

### 3) 使用本地 TTS 与 FFmpeg

```bash
python scripts/run_case.py \
  --case cases/case_001.md \
  --tts-provider local \
  --video-provider ffmpeg \
  --fallback-to-mock
```

## 输出说明
执行完成后会在 `output/case_001/` 看到：
- `script_60s.md`
- `voiceover.txt`
- `subtitles.srt`
- `shots.json`
- `run.log`

mock 渲染产物：
- `images/*.txt`
- `audio/voice.txt`
- `final.mock.txt`

真实 provider（可用时）产物：
- `audio/voice.wav`
- `final.mp4`

## 工作流
1. `parse_case`: 读取案例并提取结构化信息。
2. `generate_materials`: 生成脚本、配音稿、字幕、镜头清单。
3. `render_images`: 走图片 provider（当前 mock）。
4. `render_audio`: 支持 `mock` / `local`。
5. `render_video`: 支持 `mock` / `ffmpeg`。
6. `pipeline`: 串联全流程并记录日志。

## 测试

```bash
python -m pytest -q
```
