#!/usr/bin/env python3
"""
券商研報抓取器 (Report Fetcher) v1.0
從東方財富研報中心拉取全量行業研報（qType=1），排除定期報告與非券商源。

用法:
  python scripts/fetch_reports.py --days 7          # 近7天窗口（預設）
  python scripts/fetch_reports.py --days 1 --limit 5 # 小批量冒煙測試
  python scripts/fetch_reports.py --output manifest/pending.json

規則來源: topic-ana（東方財富 REST API + 排除詞表）
本腳本獨立實作，不依賴 topic-ana 程式碼。
"""

import argparse
import datetime
import json
import sys

import requests

API_BASE = "https://reportapi.eastmoney.com/report/list"
PDF_URL_TMPL = "https://pdf.dfcfw.com/pdf/H3_{info_code}_1.pdf"

# 標題命中以下詞 = 定期彙報，不做全文轉檔
EXCLUDE_TITLE_PATTERNS = [
    "周報", "周度", "周觀點", "雙周報", "雙周談",
    "日報", "晨報",
    "月報", "月度", "月跟蹤",
    "行業跟蹤",
    "行業周度",
    "季報", "季度",
]

# 出現在數據中但非標準券商的源（諮詢公司、企業、媒體等），過濾掉
NON_BROKER_ORGS = [
    "頭豹研究院", "碩遠諮詢", "蔚雲出海", "世界銀行",
    "攜程集團", "淘天", "阿里巴巴", "億歐智庫",
    "創業邦", "科睿唯安", "怡安企業服務",
    "前哨", "摩熵數科", "杭州非凡影視", "深圳市中安",
    "北京易觀數智", "中國化工學會", "愈到集團", "天貓",
    "灼識投資諮詢", "艾瑞",
]


def is_broker(org_name: str) -> bool:
    for nb in NON_BROKER_ORGS:
        if nb in org_name:
            return False
    return True


def is_excluded_report(title: str) -> bool:
    for p in EXCLUDE_TITLE_PATTERNS:
        if p in title:
            return True
    return False


def fetch_reports(days: int) -> list:
    """從東財 API 拉取近 days 天的全部研報（翻頁）"""
    end_date = datetime.date.today()
    begin_date = end_date - datetime.timedelta(days=days)
    all_data = []
    page = 1
    total_pages = 1

    while page <= total_pages:
        url = (f"{API_BASE}?industryCode=*&pageSize=50&industry=*"
               f"&rating=*&ratingChange=*&beginTime={begin_date}"
               f"&endTime={end_date}&pageNo={page}&fields=&qType=1"
               f"&orgCode=&rcode=")
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if page == 1:
            total_pages = data.get("TotalPage", 1)
            print(f"  時間範圍: {begin_date} ~ {end_date}", file=sys.stderr)
            print(f"  總報告數: {data.get('hits', '?')} 條, 共 {total_pages} 頁",
                  file=sys.stderr)
        all_data.extend(data.get("data", []))
        page += 1
    return all_data


def select_reports(reports: list) -> list:
    """過濾非券商 + 排除定期彙報，輸出結構化清單"""
    selected = []
    for r in reports:
        org = r.get("orgSName", "")
        if not is_broker(org):
            continue
        title = r.get("title", "")
        if is_excluded_report(title):
            continue
        info_code = r.get("infoCode", "")
        if not info_code:
            continue
        selected.append({
            "infoCode": info_code,
            "title": title,
            "industryName": r.get("industryName", ""),
            "orgSName": org,
            "publishDate": r.get("publishDate", ""),
            "attachPages": r.get("attachPages", 0),
            "attachSize": r.get("attachSize", 0),
            "pdf_url": PDF_URL_TMPL.format(info_code=info_code),
        })
    return selected


def main():
    parser = argparse.ArgumentParser(
        description="券商研報抓取器 — 東財全量行業研報清單"
    )
    parser.add_argument("--days", type=int, default=7,
                        help="近幾日窗口（預設 7）")
    parser.add_argument("--limit", type=int, default=0,
                        help="限制輸出條數（0=全量，冒煙測試用）")
    parser.add_argument("--output", default="manifest/pending.json",
                        help="輸出 JSON 路徑（預設 manifest/pending.json）")
    args = parser.parse_args()

    print(f"🔍 抓取近 {args.days} 天行業研報清單...", file=sys.stderr)
    reports = fetch_reports(days=args.days)
    print(f"📡 API 原始: {len(reports)} 條", file=sys.stderr)

    selected = select_reports(reports)
    print(f"📡 排除定期彙報/非券商後: {len(selected)} 篇", file=sys.stderr)

    if args.limit > 0:
        selected = selected[: args.limit]
        print(f"   --limit 截斷至 {args.limit} 篇", file=sys.stderr)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(selected, f, ensure_ascii=False, indent=2)
    print(f"✅ 已寫入 {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
