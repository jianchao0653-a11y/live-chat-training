# CLAUDE.md

## 项目目标
这是一个个人本地使用的中文法律案例短视频生产执行器，优先保证：
- 可运行
- 可复现
- 可扩展
- 输出可审阅

## 开发约束
1. V1 优先命令行，不做前端优先设计。
2. 所有步骤模块化，避免耦合。
3. provider 必须可替换，默认提供 mock。
4. 文件编码统一 UTF-8。
5. Windows 路径兼容（统一使用 `pathlib.Path`）。
6. 错误不可静默，异常需向上抛出并写入日志。

## 当前流程
- `parse_case` -> `generate_materials` -> `render_images` -> `render_audio` -> `render_video`
- 入口：`scripts/run_case.py`
- 编排：`app/pipeline.py`

## 输出规范
每次运行至少输出：
- `script_60s.md`
- `voiceover.txt`
- `subtitles.srt`
- `shots.json`
- `run.log`

## 文案风格
- 冷静、克制、清楚
- 不虚构事实
- 不擅自增加法律结论
- 风险提醒导向
