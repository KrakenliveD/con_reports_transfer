#!/usr/bin/env python3
"""
券商研報抓取器 (Report Fetcher) v1.1
從研報中心拉取全量行業研報清單（qType=1），排除定期彙報與非券商源。

用法:
  python scripts/fetch_reports.py --days 7          # 近7天窗口（預設）
  python scripts/fetch_reports.py --days 1 --limit 5 # 小批量冒煙測試
  python scripts/fetch_reports.py --output manifest/pending.json

必要環境變數:
  REPORT_API_BASE   研報列表 API 端點（本機 .env / GitHub Secret）

規則來源: 彙整自既有抓取規則（REST API + 排除詞表）。
本腳本獨立實作，不依賴其他專案程式碼。
"""

import argparse
import datetime
import json
import sys
from pathlib import Path

import requests

from config import require

API_BASE = require("REPORT_API_BASE")

# 標題命中以下詞 = 定期彙報，不做全文轉檔
# 2026-08-17：詞表由繁體改為簡體（東財 API 標題為簡體，原繁體詞表完全失效，
# 導致 47% 定期彙報漏網轉檔）。與下游 topic-mining 的 EXCLUDE_TITLE_PATTERNS 保持一致。
EXCLUDE_TITLE_PATTERNS = [
    "周报", "周度", "周观点", "双周报", "双周谈",
    "日报", "晨报",
    "月报", "月度", "月跟踪",
    "行业跟踪",
    "行业周度",
    "季报", "季度",
]

# 出現在數據中但非標準券商的源（諮詢公司、企業、媒體等），過濾掉
# 2026-08-17：詞表由繁體改為簡體（東財 API 機構名為簡體，原繁體詞表全部失效）；
# 並按真實數據補錄吉圖諮詢/尼爾森/飛瓜數據等非券商。
NON_BROKER_ORGS = [
    "硕远咨询", "蔚云出海", "世界银行",
    "携程集团", "淘天", "阿里巴巴", "亿欧智库",
    "创业邦", "科睿唯安", "怡安企业服务",
    "前哨", "摩熵数科", "杭州非凡影视", "深圳市中安",
    "北京易观数智", "中国化工学会", "愈到集团", "天猫",
    "灼识投资咨询", "艾瑞",
    # 2026-08-17 實測漏網補錄
    "吉图企业管理咨询", "尼尔森", "飞瓜数据",
    "中国电力企业联合会", "中国汽车流通协会", "世界黄金协会",
    "国际能源署", "北京航空航天大学",
    "首都医科大学附属", "欧洲疾病预防控制中心", "美国农业部",
    "普罗维植", "一带一路", "语言教育文化组织联盟",
    "上海市住房和城乡建设管理委员会",
    "北京智信联成管理咨询", "北京顺为人和企业咨询",
    "上海嘉世营销咨询", "天津三十六颗心科技", "顺网科技",
    "杭州知衣科技", "南京掌控网络科技", "驱动视界", "华为数字能源",
    "中国联通", "加特纳", "亿邦动力", "Brand Finance", "Common Sense",
    # 含「证券」字樣但非券商的媒體/網站（白名單例外覆蓋）
    "证券时报", "证券日报", "证券之星",
]

# 2026-08-17 白名單化：券商判定由「黑名單排除」改為「白名單命中」。
# 實測 corpus 74 家機構中 42 家為非券商（協會/研究院/大學/政府/諮詢/科技/媒體），
# 黑名單逐一排除難以維繫。新規則：名稱含「证券」或命中已知券商縮寫；
# 加上精選研究機構白名單（RESEARCH_ORGS，數據驅動挑選——其報告實測承載信號關鍵字，
# 如中证鹏元储能10.0、头豹棉纺织6.0、国家能源局储能3.5、涌益生猪产能2.5）。
# NON_BROKER_ORGS 保留為例外覆蓋（優先檢查，防「证券时报」等含证券字樣的非券商）。
BROKER_KEYWORDS = ["证券"]
BROKER_ABBREV = ["中金", "国泰君安", "太平洋", "申万宏源"]

# 精選研究機構白名單（非券商但產出前瞻產業/信用研究，實測承載信號）：
# 中证鹏元/联合资信(評級) 中国信通院/国家能源局(官方權威) 清华大学(學術)
# 头豹研究院/甲子光年/腾讯研究院(產業智庫) 源达信息(投資諮詢) 涌益(農業高頻草根數據)
RESEARCH_ORGS = [
    "中证鹏元", "联合资信", "中国信通院", "国家能源局", "清华大学",
    "头豹研究院", "甲子光年", "腾讯研究院", "源达信息", "涌益",
]


def is_research_org(org_name: str) -> bool:
    for nb in NON_BROKER_ORGS:
        if nb in org_name:
            return False
    if any(k in org_name for k in BROKER_KEYWORDS):
        return True
    if any(a in org_name for a in BROKER_ABBREV):
        return True
    return any(r in org_name for r in RESEARCH_ORGS)


def is_excluded_report(title: str) -> bool:
    for p in EXCLUDE_TITLE_PATTERNS:
        if p in title:
            return True
    return False


def fetch_reports(days: int) -> list:
    """從研報列表 API 拉取近 days 天的全部研報（翻頁）"""
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
        if not is_research_org(org):
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
            "ratingChange": r.get("ratingChange", 0),
        })
    return selected


def main():
    parser = argparse.ArgumentParser(
        description="券商研報抓取器 — 全量行業研報清單"
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

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(selected, f, ensure_ascii=False, indent=2)
    print(f"✅ 已寫入 {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
