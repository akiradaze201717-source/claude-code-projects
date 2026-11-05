"""reports/dashboard_builder.py のスモークテスト。生成HTMLに主要数値・口座名が含まれることを確認する。"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from balances.accounts import Account
from reports.dashboard_builder import build_dashboard, expense_category_totals

ACCOUNTS = {
    "sbi_sec": Account("sbi_sec", "SBI証券", "asset", "証券", "manual"),
    "smbc_card": Account("smbc_card", "三井住友カード", "liability", "クレジットカード", "manual"),
}

SNAPSHOTS = [
    {"date": "2026-08-24", "account_id": "sbi_sec", "balance": 900000},
    {"date": "2026-08-24", "account_id": "smbc_card", "balance": 20000},
    {"date": "2026-08-31", "account_id": "sbi_sec", "balance": 1000000},
    {"date": "2026-08-31", "account_id": "smbc_card", "balance": 30000},
]

TRANSACTIONS = [
    {
        "hash": "a1",
        "issuer": "smbc",
        "txn_date": "2026-08-15",
        "amount": 3200,
        "description": "セブン-イレブン",
        "category": "食費",
        "source_file": "f.csv",
        "imported_at": "x",
    },
    {
        "hash": "a2",
        "issuer": "smbc",
        "txn_date": "2026-08-16",
        "amount": 500,
        "description": "謎の店",
        "category": "未分類",
        "source_file": "f.csv",
        "imported_at": "x",
    },
]


class TestBuildDashboard:
    def test_contains_account_names(self):
        html = build_dashboard(
            ACCOUNTS, SNAPSHOTS, TRANSACTIONS, generated_at=datetime(2026, 8, 31, 21, 0)
        )
        assert "SBI証券" in html
        assert "三井住友カード" in html

    def test_contains_net_worth(self):
        html = build_dashboard(
            ACCOUNTS, SNAPSHOTS, TRANSACTIONS, generated_at=datetime(2026, 8, 31, 21, 0)
        )
        # 純資産 = 1000000 - 30000 = 970000
        assert "970,000" in html

    def test_contains_wow_change(self):
        html = build_dashboard(
            ACCOUNTS, SNAPSHOTS, TRANSACTIONS, generated_at=datetime(2026, 8, 31, 21, 0)
        )
        # 前週純資産 = 900000-20000=880000, 今週970000 -> +90,000
        assert "90,000" in html

    def test_uncategorized_transaction_flagged(self):
        html = build_dashboard(
            ACCOUNTS, SNAPSHOTS, TRANSACTIONS, generated_at=datetime(2026, 8, 31, 21, 0)
        )
        assert "未分類" in html

    def test_empty_snapshots_no_crash(self):
        html = build_dashboard(ACCOUNTS, [], [], generated_at=datetime(2026, 8, 31, 21, 0))
        assert "資産管理ダッシュボード" in html

    def test_valid_html_structure(self):
        html = build_dashboard(
            ACCOUNTS, SNAPSHOTS, TRANSACTIONS, generated_at=datetime(2026, 8, 31, 21, 0)
        )
        assert html.startswith("<!DOCTYPE html>")
        assert html.rstrip().endswith("</html>")


class TestExpenseCategoryTotals:
    def test_aggregates_by_category(self):
        from datetime import date

        totals = expense_category_totals(TRANSACTIONS, since=date(2026, 8, 1))
        totals_dict = dict(totals)
        assert totals_dict["食費"] == 3200
        assert totals_dict["未分類"] == 500

    def test_excludes_older_than_since(self):
        from datetime import date

        totals = expense_category_totals(TRANSACTIONS, since=date(2026, 8, 20))
        totals_dict = dict(totals)
        assert "食費" not in totals_dict
