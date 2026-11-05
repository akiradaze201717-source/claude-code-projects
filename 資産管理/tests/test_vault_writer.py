"""vault_writer.py のユニットテスト。"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from balances.accounts import Account
from balances.commit import CommitResult
from balances.networth import NetWorthResult
from vault_writer import write_weekly_summary

ACCOUNTS = {
    "sbi_sec": Account("sbi_sec", "SBI証券", "asset", "証券", "manual"),
    "smbc_card": Account("smbc_card", "三井住友カード", "liability", "クレジットカード", "manual"),
}


def _result(wow=90000.0):
    networth = NetWorthResult(
        date="2026-08-31",
        total_assets=1000000.0,
        total_liabilities=30000.0,
        net_worth=970000.0,
        by_account={"sbi_sec": 1000000.0, "smbc_card": 30000.0},
    )
    return CommitResult(
        snapshot_date="2026-08-31", networth=networth, wow_change=wow, template_path=None
    )


class TestWriteWeeklySummary:
    def test_creates_note_with_frontmatter(self, tmp_path):
        out = write_weekly_summary(
            tmp_path, _result(), ACCOUNTS, [("食費", 12000.0)], "dashboard.html"
        )
        content = out.read_text(encoding="utf-8")
        assert content.startswith("---\n")
        assert "net_worth: 970000" in content
        assert "total_assets: 1000000" in content
        assert "tags:" in content
        assert "資産管理" in content

    def test_filename_uses_date(self, tmp_path):
        out = write_weekly_summary(tmp_path, _result(), ACCOUNTS, [], "dashboard.html")
        assert out.name == "2026-08-31_週次資産サマリー.md"
        assert out.parent == tmp_path / "資産管理" / "週次サマリー"

    def test_body_contains_account_breakdown(self, tmp_path):
        out = write_weekly_summary(tmp_path, _result(), ACCOUNTS, [], "dashboard.html")
        content = out.read_text(encoding="utf-8")
        assert "SBI証券" in content
        assert "三井住友カード" in content
        assert "¥1,000,000" in content

    def test_first_commit_no_wow_shows_placeholder(self, tmp_path):
        out = write_weekly_summary(tmp_path, _result(wow=None), ACCOUNTS, [], "dashboard.html")
        content = out.read_text(encoding="utf-8")
        assert "初回のため比較なし" in content
        assert "wow_change: null" in content
