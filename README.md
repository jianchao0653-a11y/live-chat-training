# live-chat-training
直播私聊训练系统

---

# 《南山知止录》案例抓取系统（执行版）

本仓库已补充一套可执行抓取脚本：`case_fetcher.py`。

## 目标流程

阅读器页面 → Playwright 翻页 → 抓取正文 → `raw_pages/` → `raw_cases/` → `cases/` → `ingest_report.json`

## 核心能力

1. **登录态保存与复用**
   - 首次运行如果不存在登录态文件，会打开登录页并等待人工登录。
   - 登录完成后保存 `storage state` 到本地（默认：`state/login_state.json`）。
   - 后续抓取自动复用登录态，无需重复登录。

2. **阅读器翻页抓取**
   - 支持通过正文 CSS 选择器抓取内容。
   - 支持“下一页”按钮选择器自动翻页。
   - 连续检测到重复页时自动停止，避免死循环。

3. **抓取结果落盘**
   - `data/raw_pages/page_0001.txt ...`：逐页文本。
   - `data/raw_cases/book_raw_case.txt`：连续原始文本。
   - `data/cases/case_0001.txt ...`：按“案例+数字”规则拆分。
   - `data/ingest_report.json`：抓取统计与产物索引。

## 运行方式

> 先安装依赖：

```bash
pip install playwright
python -m playwright install chromium
```

> 执行抓取：

```bash
python case_fetcher.py \
  --login-url "https://example.com/login" \
  --reader-url "https://example.com/reader/book/1" \
  --page-selector ".reader-content" \
  --next-selector "button.next-page" \
  --output-root "data" \
  --storage-state "state/login_state.json"
```

如果需要可视化浏览器（便于首次调试登录），增加参数：

```bash
python case_fetcher.py ... --headed
```

## 修改说明

本次修改在不删除现有内容的前提下，新增了以下内容：

1. 新增 `case_fetcher.py`，实现“登录态保存 + 阅读器抓取 + 文本落盘 + 案例拆分 + ingest_report”完整流程。
2. 更新 `README.md`，补充项目执行说明、运行命令、输出目录说明与改动说明。

## 自检建议

```bash
python -m py_compile case_fetcher.py
python case_fetcher.py --help
```

