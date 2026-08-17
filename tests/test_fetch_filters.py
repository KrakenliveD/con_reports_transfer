#!/usr/bin/env python3
"""fetch_reports 過濾邏輯單元測試（標準庫，無網絡請求）。

重點防回歸：東財 API 標題為簡體，定期彙報排除詞表必須用簡體，
否則「周報/日報/月報/季報/行業跟蹤」等全部漏網轉檔（2026-08-17 實測 47%）。

用法: python -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
os.environ.setdefault("REPORT_API_BASE", "https://example.invalid/report")

from fetch_reports import (
    EXCLUDE_TITLE_PATTERNS,
    is_excluded_report,
    is_research_org,
    select_reports,
)


class TestExcludePatterns(unittest.TestCase):
    def test_has_simplified_variants(self):
        """詞表必須包含簡體變體（API 標題為簡體）"""
        for simp in ["周报", "日报", "月报", "季报", "行业跟踪", "晨报"]:
            self.assertIn(simp, EXCLUDE_TITLE_PATTERNS,
                          f"詞表缺少簡體詞: {simp}")

    def test_simplified_periodic_titles_excluded(self):
        """簡體定期彙報標題必須被排除（真實 API 標題樣例）"""
        samples = [
            "电力设备及新能源行业周报：硅料龙头签署反内卷倡议书",
            "计算机行业周报：算租，NEOCLOUD不输CLOUD",
            "科技行业月报：科技板块震荡，AI资本支出进一步上调",
            "医药健康投融资&交易月报2026年07月",
            "仿制药月报2026年7月",
            "建筑装饰行业行业跟踪报告",
            "房地产行业第32周周报：新房成交同比降幅扩大",
        ]
        for t in samples:
            self.assertTrue(is_excluded_report(t), f"應排除但漏網: {t}")

    def test_non_periodic_titles_kept(self):
        """非定期深研標題不應被排除"""
        samples = [
            "电力设备与新能源行业研究：英伟达电源白皮书更新",
            "半导体材料涨价深度报告",
            "机器人行业研究：宇树科技IPO申购创纪录",
            "银行行业深度：负债成本改善利好息差",
        ]
        for t in samples:
            self.assertFalse(is_excluded_report(t), f"不應排除: {t}")


class TestNonBroker(unittest.TestCase):
    def test_non_broker_filtered(self):
        """簡體非券商機構必須被過濾（2026-08-17 前繁體詞表全部失效）"""
        self.assertFalse(is_research_org("蔚云出海(广州)企业咨询"))
        self.assertFalse(is_research_org("摩熵数科(成都)医药科技"))
        self.assertFalse(is_research_org("广州市吉图企业管理咨询"))
        self.assertFalse(is_research_org("尼尔森"))
        self.assertFalse(is_research_org("飞瓜数据"))
        self.assertFalse(is_research_org("艾瑞"))

    def test_broker_kept(self):
        self.assertTrue(is_research_org("国信证券"))
        self.assertTrue(is_research_org("中金公司"))
        self.assertTrue(is_research_org("东吴证券"))

    def test_broker_allowlist_by_keyword(self):
        """白名單：名稱含「证券」即視為券商"""
        for org in ["国新证券股份", "国投证券(香港)", "交银国际证券", "中银证券"]:
            self.assertTrue(is_research_org(org), f"應視為券商: {org}")

    def test_broker_allowlist_by_abbrev(self):
        """白名單：已知券商縮寫（名稱不含「证券」）"""
        for org in ["中金公司", "国泰君安", "太平洋", "申万宏源"]:
            self.assertTrue(is_research_org(org), f"應視為券商: {org}")

    def test_research_org_allowlist(self):
        """精選研究機構白名單：數據驅動挑選的10家非券商保留"""
        for org in ["中证鹏元", "联合资信评估", "中国信通院", "国家能源局",
                    "清华大学", "头豹研究院", "甲子光年智库", "腾讯研究院",
                    "源达信息", "山东涌益信息咨询"]:
            self.assertTrue(is_research_org(org), f"應視為研究機構: {org}")

    def test_non_research_org_no_security_keyword(self):
        """非券商亦非精選研究機構者一律排除（默認拒絕）"""
        for org in ["广州市吉图企业管理咨询", "尼尔森", "中国电力企业联合会",
                    "华为数字能源技术", "蔚云出海(广州)企业咨询", "世界银行"]:
            self.assertFalse(is_research_org(org), f"應過濾: {org}")

    def test_broker_blacklist_override(self):
        """黑名單覆蓋白名單：含「证券」字樣的非券商媒體仍排除"""
        self.assertFalse(is_research_org("证券时报"))


class TestSelectReports(unittest.TestCase):
    def _reports(self):
        return [
            {"infoCode": "A1", "title": "计算机行业周报：算租",
             "orgSName": "国信证券", "industryName": "计算机"},
            {"infoCode": "A2", "title": "半导体材料涨价深度",
             "orgSName": "中银证券", "industryName": "电子"},
            {"infoCode": "A3", "title": "金融科技行业跟踪",
             "orgSName": "华泰证券", "industryName": "计算机"},
            {"infoCode": "A4", "title": "蔚云出海行业研究",
             "orgSName": "蔚云出海(广州)企业咨询", "industryName": "未知"},
            {"infoCode": "A5", "title": "储能行业中期展望",
             "orgSName": "中证鹏元", "industryName": "电池"},
            {"infoCode": "", "title": "无infoCode应丢弃",
             "orgSName": "国金证券", "industryName": "未知"},
        ]

    def test_periodic_and_non_broker_excluded(self):
        selected = select_reports(self._reports())
        codes = {r["infoCode"] for r in selected}
        self.assertIn("A2", codes)          # 深研保留
        self.assertIn("A5", codes)          # 精選研究機構（中证鹏元）保留
        self.assertNotIn("A1", codes)       # 周报排除
        self.assertNotIn("A3", codes)       # 行业跟踪排除
        self.assertNotIn("A4", codes)       # 非券商/非研究機構排除
        self.assertNotIn("", codes)         # 空 infoCode 排除


if __name__ == "__main__":
    unittest.main()