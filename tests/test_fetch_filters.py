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
    is_broker,
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
        self.assertFalse(is_broker("头豹研究院"))
        self.assertFalse(is_broker("蔚云出海(广州)企业咨询"))
        self.assertFalse(is_broker("摩熵数科(成都)医药科技"))
        self.assertFalse(is_broker("广州市吉图企业管理咨询"))
        self.assertFalse(is_broker("尼尔森"))
        self.assertFalse(is_broker("飞瓜数据"))
        self.assertFalse(is_broker("艾瑞"))

    def test_broker_kept(self):
        self.assertTrue(is_broker("国信证券"))
        self.assertTrue(is_broker("中金公司"))
        self.assertTrue(is_broker("东吴证券"))


class TestSelectReports(unittest.TestCase):
    def _reports(self):
        return [
            {"infoCode": "A1", "title": "计算机行业周报：算租",
             "orgSName": "国信证券", "industryName": "计算机"},
            {"infoCode": "A2", "title": "半导体材料涨价深度",
             "orgSName": "中银证券", "industryName": "电子"},
            {"infoCode": "A3", "title": "金融科技行业跟踪",
             "orgSName": "华泰证券", "industryName": "计算机"},
            {"infoCode": "A4", "title": "头豹行业研究",
             "orgSName": "头豹研究院", "industryName": "未知"},
            {"infoCode": "", "title": "无infoCode应丢弃",
             "orgSName": "国金证券", "industryName": "未知"},
        ]

    def test_periodic_and_non_broker_excluded(self):
        selected = select_reports(self._reports())
        codes = {r["infoCode"] for r in selected}
        self.assertIn("A2", codes)          # 深研保留
        self.assertNotIn("A1", codes)       # 周报排除
        self.assertNotIn("A3", codes)       # 行业跟踪排除
        self.assertNotIn("A4", codes)       # 非券商排除
        self.assertNotIn("", codes)         # 空 infoCode 排除


if __name__ == "__main__":
    unittest.main()