#!/usr/bin/env python3
"""
券商研報 PDF → Markdown 轉換器 (PDF Converter) v1.0
讀取 manifest/pending.json，對「尚未下載」的報告：
  1. 下載 PDF (pdf.dfcfw.com)
  2. pymupdf 純文字提取 → 平鋪寫入 reports/{infoCode}_{title}.md
  3. 更新 manifest/downloaded.json（去重）

用法:
  python scripts/convert_pdf.py

依賴: pymupdf requests
"""

import json
import os
import sys
import time
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_DIR = REPO_ROOT / "manifest"
REPORTS_DIR = REPO_ROOT / "reports"

PENDING_FILE = MANIFEST_DIR / "pending.json"
DOWNLOADED_FILE = MANIFEST_DIR / "downloaded.json"

PDF_BASE_URL = "https://pdf.dfcfw.com/pdf/H3_{infoCode}_1.pdf"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://data.eastmoney.com/",
}
DELAY = 0.5  # 秒，對東財伺服器禮貌


def load_json(path: Path, default=None):
    if not path.exists():
        return default if default is not None else []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  📝 更新 {path.name}", file=sys.stderr)


def get_downloaded_set():
    data = load_json(DOWNLOADED_FILE, default={"downloaded": []})
    if isinstance(data, list):
        return set(data)
    return set(data.get("downloaded", []))


def save_downloaded_set(codes: set):
    save_json(DOWNLOADED_FILE, {"downloaded": sorted(codes)})


def download_pdf(info_code: str) -> bytes:
    url = f"{PDF_BASE_URL.format(infoCode=info_code)}?{int(time.time()*1000)}.pdf"
    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    if "application/pdf" not in resp.headers.get("content-type", ""):
        raise RuntimeError(f"非 PDF 回應 (status={resp.status_code})")
    return resp.content


def pdf_to_markdown(pdf_bytes: bytes, report: dict) -> str:
    import pymupdf  # 延遲匯入，僅轉檔時需要

    ic = report.get("infoCode", "")
    title = report.get("title", "Untitled")
    industry = report.get("industryName", "")
    org = report.get("orgSName", "")
    publish_date = report.get("publishDate", "")
    pages = report.get("attachPages", 0)

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    text = "\n".join(page.get_text() for page in doc)
    doc.close()

    pdf_url = PDF_BASE_URL.format(infoCode=ic)
    md = f"# {title}\n\n"
    md += f"> **原始 PDF**：[下載]({pdf_url})  \n"
    md += f"> **infoCode**：`{ic}`  \n"
    md += f"> **行業**：{industry}  |  **機構**：{org}  \n"
    if publish_date:
        md += f"> **日期**：{publish_date[:10]}  \n"
    md += f"> **頁數**：{pages}\n\n"
    md += "---\n\n"
    md += text
    return md


def safe_filename(info_code: str, title: str, max_title_len: int = 40) -> str:
    safe = title.strip().replace("/", "_").replace("\\", "_")
    safe = safe.replace(" ", "_").replace(":", "_").replace('"', "")
    safe = safe.replace("?", "").replace("*", "").replace("<", "").replace(">", "")
    safe = safe.replace("|", "")
    if len(safe) > max_title_len:
        safe = safe[:max_title_len]
    return f"{info_code}_{safe}.md"


def main():
    pending = load_json(PENDING_FILE, default=[])
    if isinstance(pending, dict) and "reports" in pending:
        pending = pending["reports"]
    if not pending:
        print("✅ pending.json 為空或不存在，無需轉檔。", file=sys.stderr)
        return

    downloaded_set = get_downloaded_set()
    new_reports = [
        r for r in pending
        if r.get("infoCode") and r["infoCode"] not in downloaded_set
    ]
    print(f"📋 待處理: {len(pending)} | 已下載: {len(downloaded_set)} | "
          f"新報告: {len(new_reports)}", file=sys.stderr)
    if not new_reports:
        print("✅ 沒有新報告需要處理。", file=sys.stderr)
        return

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    success, failed = [], []

    for i, report in enumerate(new_reports, 1):
        ic = report.get("infoCode", "")
        title = report.get("title", "Untitled")
        print(f"\n[{i}/{len(new_reports)}] [{ic}] {title[:60]}", file=sys.stderr)
        try:
            pdf_bytes = download_pdf(ic)
            print(f"  ⬇️  PDF 下載完成 ({len(pdf_bytes)/1024/1024:.1f}MB)",
                  file=sys.stderr)
            md_content = pdf_to_markdown(pdf_bytes, report)
            fname = safe_filename(ic, title)
            (REPORTS_DIR / fname).write_text(md_content, encoding="utf-8")
            cn_chars = sum(1 for c in md_content if '\u4e00' <= c <= '\u9fff')
            print(f"  📄 {fname} ({len(md_content)} chars, {cn_chars} 中文字)",
                  file=sys.stderr)
            downloaded_set.add(ic)
            success.append(ic)
        except Exception as e:
            print(f"  ❌ 失敗: {e}", file=sys.stderr)
            failed.append({"infoCode": ic, "title": title, "error": str(e)})
        time.sleep(DELAY)

    save_downloaded_set(downloaded_set)
    print(f"\n{'=' * 50}", file=sys.stderr)
    print(f"✅ 成功: {len(success)} 篇", file=sys.stderr)
    if failed:
        print(f"❌ 失敗: {len(failed)} 篇", file=sys.stderr)
        for f in failed:
            print(f"   [{f['infoCode']}] {f['error']}", file=sys.stderr)
        sys.exit(1)
    else:
        print("🎉 全部完成！", file=sys.stderr)


if __name__ == "__main__":
    main()
