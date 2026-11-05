"""balances/networth.py のユニットテスト。"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from balances.accounts import Account
from balances.networth import compute_networth, week_over_week_change

ACCOUNTS = {
    "sbi_sec": Account("sbi_sec", "SBI証券", "asset", "証券", "manual"),
    "paypay": Account("paypay", "PayPay", "asset", "ウォレット", "manual"),
    "smbc_card": Account("smbc_card", "三井住友カード", "liability", "クレジットカード", "manual"),
}


class TestComputeNetworth:
    def test_assets_and_liabilities_summed_correctly(self):
        entries = [
            {"account_id": "sbi_sec", "balance": 1000000},
            {"account_id": "paypay", "balance": 50000},
            {"account_id": "smbc_card", "balance": 30000},
        ]
        result = compute_networth("2026-08-31", entries, ACCOUNTS)
        assert result.total_assets == 1050000
        assert result.total_liabilities == 30000
        assert result.net_worth == 1020000

    def test_liabilities_exceed_assets_gives_negative_networth(self):
        entries = [
            {"account_id": "paypay", "balance": 1000},
            {"account_id": "smbc_card", "balance": 50000},
        ]
        result = compute_networth("2026-08-31", entries, ACCOUNTS)
        assert result.net_worth == -49000

    def test_unknown_account_id_ignored(self):
        entries = [
            {"account_id": "sbi_sec", "balance": 100},
            {"account_id": "no_such_account", "balance": 999999},
        ]
        result = compute_networth("2026-08-31", entries, ACCOUNTS)
        assert result.total_assets == 100

    def test_by_account_breakdown(self):
        entries = [{"account_id": "sbi_sec", "balance": 100}]
        result = compute_networth("2026-08-31", entries, ACCOUNTS)
        assert result.by_account == {"sbi_sec": 100.0}

    def test_empty_entries_gives_zero_networth(self):
        result = compute_networth("2026-08-31", [], ACCOUNTS)
        assert result.net_worth == 0
        assert result.total_assets == 0
        assert result.total_liabilities == 0


class TestWeekOverWeekChange:
    def test_no_previous_returns_none(self):
        current = compute_networth(
            "2026-08-31", [{"account_id": "sbi_sec", "balance": 100}], ACCOUNTS
        )
        assert week_over_week_change(current, None) is None

    def test_positive_change(self):
        prev = compute_networth("2026-08-24", [{"account_id": "sbi_sec", "balance": 100}], ACCOUNTS)
        curr = compute_networth("2026-08-31", [{"account_id": "sbi_sec", "balance": 150}], ACCOUNTS)
        assert week_over_week_change(curr, prev) == 50

    def test_negative_change(self):
        prev = compute_networth("2026-08-24", [{"account_id": "sbi_sec", "balance": 150}], ACCOUNTS)
        curr = compute_networth("2026-08-31", [{"account_id": "sbi_sec", "balance": 100}], ACCOUNTS)
        assert week_over_week_change(curr, prev) == -50
