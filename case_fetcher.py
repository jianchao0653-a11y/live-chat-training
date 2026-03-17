#!/usr/bin/env python3
"""《南山知止录》案例抓取系统

功能概览：
1. 通过 Playwright 首次登录并保存 storage state。
2. 使用保存的登录状态访问阅读器并自动翻页抓取正文。
3. 将抓取结果输出到 raw_pages/。
4. 将连续正文输出到 raw_cases/。
5. 按简单规则拆分到 cases/。
6. 生成 ingest_report.json。

说明：
- 本脚本不会删除任何已有目录中的文件。
- 为避免重复抓取，脚本会对相邻重复页进行去重。
"""

from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List



def get_sync_playwright():
    from playwright.sync_api import sync_playwright

    return sync_playwright



@dataclass
class ScrapeConfig:
    login_url: str
    reader_url: str
    output_root: Path
    storage_state_path: Path
    page_selector: str
    next_button_selector: str
    max_pages: int
    timeout_ms: int
    headless: bool


def ensure_dirs(output_root: Path) -> dict[str, Path]:
    paths = {
        "raw_pages": output_root / "raw_pages",
        "raw_cases": output_root / "raw_cases",
        "cases": output_root / "cases",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def normalize_text(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact


def capture_login_state(config: ScrapeConfig) -> None:
    print("[login] 未找到登录态，开始首次登录流程...")
    with get_sync_playwright()() as p:
        browser = p.chromium.launch(headless=config.headless)
        context = browser.new_context()
        page = context.new_page()
        page.goto(config.login_url, wait_until="domcontentloaded", timeout=config.timeout_ms)
        print("[login] 请在打开的页面中完成登录，然后按回车继续保存登录态。")
        input()
        context.storage_state(path=str(config.storage_state_path))
        print(f"[login] 登录态已保存: {config.storage_state_path}")
        context.close()
        browser.close()


def open_authenticated_context(config: ScrapeConfig):
    if not config.storage_state_path.exists():
        capture_login_state(config)

    playwright = get_sync_playwright()().start()
    browser = playwright.chromium.launch(headless=config.headless)
    context = browser.new_context(storage_state=str(config.storage_state_path))

    # 将关闭逻辑绑定到对象上，便于统一清理
    context._playwright = playwright  # type: ignore[attr-defined]
    context._browser = browser  # type: ignore[attr-defined]
    return context


def close_authenticated_context(context) -> None:
    browser = getattr(context, "_browser", None)
    playwright = getattr(context, "_playwright", None)
    try:
        context.close()
    finally:
        if browser is not None:
            browser.close()
        if playwright is not None:
            playwright.stop()


def extract_page_text(page, selector: str) -> str:
    # 尝试多个抓取方式，提升阅读器页面适配能力
    locator = page.locator(selector)
    if locator.count() > 0:
        text = locator.first.inner_text(timeout=3000)
        return normalize_text(text)

    # 回退：抓整页文本
    text = page.inner_text("body", timeout=3000)
    return normalize_text(text)


def click_next(page, next_selector: str, timeout_ms: int) -> bool:
    btn = page.locator(next_selector)
    if btn.count() == 0:
        return False
    if not btn.first.is_enabled():
        return False

    before = page.url
    btn.first.click(timeout=timeout_ms)
    page.wait_for_timeout(600)
    try:
        page.wait_for_load_state("domcontentloaded", timeout=2500)
    except Exception:
        pass
    after = page.url

    # 阅读器可能不变更 URL，此处允许继续
    return before != after or True


def scrape_reader_pages(config: ScrapeConfig) -> List[str]:
    context = open_authenticated_context(config)
    pages_text: List[str] = []

    try:
        page = context.new_page()
        page.goto(config.reader_url, wait_until="domcontentloaded", timeout=config.timeout_ms)
        page.wait_for_timeout(1200)

        last_text = ""
        stagnant_rounds = 0

        for idx in range(config.max_pages):
            text = extract_page_text(page, config.page_selector)
            if not text:
                print(f"[scrape] 第 {idx + 1} 页为空，停止。")
                break

            if text == last_text:
                stagnant_rounds += 1
            else:
                stagnant_rounds = 0
                pages_text.append(text)
                last_text = text
                print(f"[scrape] 已抓取第 {len(pages_text)} 页。")

            if stagnant_rounds >= 2:
                print("[scrape] 连续检测到重复页面，判定到达末页。")
                break

            moved = click_next(page, config.next_button_selector, config.timeout_ms)
            if not moved:
                print("[scrape] 未找到可点击的下一页按钮，抓取结束。")
                break

            page.wait_for_timeout(800)

    finally:
        close_authenticated_context(context)

    return pages_text


def write_raw_pages(raw_pages_dir: Path, pages_text: Iterable[str]) -> List[Path]:
    paths: List[Path] = []
    for i, text in enumerate(pages_text, start=1):
        path = raw_pages_dir / f"page_{i:04d}.txt"
        path.write_text(text + "\n", encoding="utf-8")
        paths.append(path)
    return paths


def build_raw_case(raw_cases_dir: Path, pages_text: Iterable[str]) -> Path:
    merged = "\n\n".join(pages_text).strip() + "\n"
    out = raw_cases_dir / "book_raw_case.txt"
    out.write_text(merged, encoding="utf-8")
    return out


def split_cases(raw_case_path: Path, cases_dir: Path) -> List[Path]:
    text = raw_case_path.read_text(encoding="utf-8")
    # 规则：按“案例+数字”分段；若未匹配则保留单文件
    chunks = re.split(r"(?=案例\s*\d+)", text)
    cleaned = [c.strip() for c in chunks if c.strip()]

    outputs: List[Path] = []
    if len(cleaned) <= 1:
        single = cases_dir / "case_0001.txt"
        single.write_text(text.strip() + "\n", encoding="utf-8")
        outputs.append(single)
        return outputs

    for idx, chunk in enumerate(cleaned, start=1):
        out = cases_dir / f"case_{idx:04d}.txt"
        out.write_text(chunk + "\n", encoding="utf-8")
        outputs.append(out)

    return outputs


def write_report(output_root: Path, raw_page_files: List[Path], case_files: List[Path], started_at: float) -> Path:
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "duration_seconds": round(time.time() - started_at, 2),
        "raw_pages_count": len(raw_page_files),
        "cases_count": len(case_files),
        "raw_pages": [str(p) for p in raw_page_files],
        "cases": [str(p) for p in case_files],
    }
    report_path = output_root / "ingest_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="《南山知止录》案例抓取系统")
    parser.add_argument("--login-url", required=True, help="登录页面 URL")
    parser.add_argument("--reader-url", required=True, help="阅读器页面 URL")
    parser.add_argument("--output-root", default="data", help="输出根目录，默认 data")
    parser.add_argument("--storage-state", default="state/login_state.json", help="登录态文件路径")
    parser.add_argument("--page-selector", default=".reader-content", help="正文选择器")
    parser.add_argument("--next-selector", default="button.next-page", help="下一页按钮选择器")
    parser.add_argument("--max-pages", type=int, default=1000, help="最大翻页数量")
    parser.add_argument("--timeout-ms", type=int, default=15000, help="页面超时时间（毫秒）")
    parser.add_argument("--headed", action="store_true", help="是否显示浏览器窗口（默认无头）")
    return parser


def main() -> None:
    started_at = time.time()
    args = build_parser().parse_args()

    storage_state_path = Path(args.storage_state)
    storage_state_path.parent.mkdir(parents=True, exist_ok=True)

    config = ScrapeConfig(
        login_url=args.login_url,
        reader_url=args.reader_url,
        output_root=Path(args.output_root),
        storage_state_path=storage_state_path,
        page_selector=args.page_selector,
        next_button_selector=args.next_selector,
        max_pages=args.max_pages,
        timeout_ms=args.timeout_ms,
        headless=not args.headed,
    )

    dirs = ensure_dirs(config.output_root)
    pages_text = scrape_reader_pages(config)
    raw_page_files = write_raw_pages(dirs["raw_pages"], pages_text)
    raw_case_path = build_raw_case(dirs["raw_cases"], pages_text)
    case_files = split_cases(raw_case_path, dirs["cases"])
    report_path = write_report(config.output_root, raw_page_files, case_files, started_at)

    print("[done] 抓取与入库原始输出完成。")
    print(f"[done] raw_pages: {len(raw_page_files)}")
    print(f"[done] cases: {len(case_files)}")
    print(f"[done] report: {report_path}")


if __name__ == "__main__":
    main()
