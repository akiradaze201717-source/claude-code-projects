"""balances/ledger.py のユニットテスト。tmp_path で実ファイルの読み書きを検証する。"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from balances.ledger import (
    append_snapshot,
    get_balances_for_date,
    get_previous_balance,
    latest_snapshot_date,
    list_snapshot_dates,
    load_snapshots,
)


class TestAppendAndLoad:
    def test_append_then_load(self, tmp_path):
        path = tmp_path / "snapshots.json"
        append_snapshot(
            "2026-08-31",
            [
                {"account_id": "sbi_sec", "balance": 100000, "source": "manual"},
            ],
            path=path,
        )
        loaded = load_snapshots(path)
        assert len(loaded) == 1
        assert loaded[0]["account_id"] == "sbi_sec"
        assert loaded[0]["balance"] == 100000

    def test_load_missing_file_returns_empty(self, tmp_path):
        path = tmp_path / "nope.json"
        assert load_snapshots(path) == []

    def test_same_day_same_account_overwrites(self, tmp_path):
        path = tmp_path / "snapshots.json"
        append_snapshot(
            "2026-08-31", [{"account_id": "sbi_sec", "balance": 100, "source": "manual"}], path=path
        )
        append_snapshot(
            "2026-08-31", [{"account_id": "sbi_sec", "balance": 200, "source": "manual"}], path=path
        )
        loaded = load_snapshots(path)
        assert len(loaded) == 1
        assert loaded[0]["balance"] == 200

    def test_different_accounts_same_day_both_kept(self, tmp_path):
        path = tmp_path / "snapshots.json"
        append_snapshot(
            "2026-08-31",
            [
                {"account_id": "sbi_sec", "balance": 100, "source": "manual"},
                {"account_id": "paypay", "balance": 50, "source": "manual"},
            ],
            path=path,
        )
        assert len(load_snapshots(path)) == 2

    def test_multiple_dates_accumulate(self, tmp_path):
        path = tmp_path / "snapshots.json"
        append_snapshot(
            "2026-08-24", [{"account_id": "sbi_sec", "balance": 100, "source": "manual"}], path=path
        )
        append_snapshot(
            "2026-08-31", [{"account_id": "sbi_sec", "balance": 110, "source": "manual"}], path=path
        )
        assert len(load_snapshots(path)) == 2

    def test_committed_at_is_recorded(self, tmp_path):
        path = tmp_path / "snapshots.json"
        append_snapshot(
            "2026-08-31", [{"account_id": "sbi_sec", "balance": 100, "source": "manual"}], path=path
        )
        assert load_snapshots(path)[0]["committed_at"]


class TestGetBalancesForDate:
    def test_returns_dict_keyed_by_account(self, tmp_path):
        path = tmp_path / "s.json"
        append_snapshot(
            "2026-08-31",
            [
                {"account_id": "sbi_sec", "balance": 100, "source": "manual"},
                {"account_id": "paypay", "balance": 50, "source": "manual"},
            ],
            path=path,
        )
        result = get_balances_for_date("2026-08-31", path=path)
        assert result["sbi_sec"]["balance"] == 100
        assert result["paypay"]["balance"] == 50

    def test_other_dates_excluded(self, tmp_path):
        path = tmp_path / "s.json"
        append_snapshot(
            "2026-08-24", [{"account_id": "sbi_sec", "balance": 90, "source": "manual"}], path=path
        )
        append_snapshot(
            "2026-08-31", [{"account_id": "sbi_sec", "balance": 100, "source": "manual"}], path=path
        )
        result = get_balances_for_date("2026-08-31", path=path)
        assert result["sbi_sec"]["balance"] == 100


class TestGetPreviousBalance:
    def test_no_history_returns_none(self, tmp_path):
        path = tmp_path / "s.json"
        assert get_previous_balance("sbi_sec", path=path) is None

    def test_returns_latest_value(self, tmp_path):
        path = tmp_path / "s.json"
        append_snapshot(
            "2026-08-17", [{"account_id": "sbi_sec", "balance": 90, "source": "manual"}], path=path
        )
        append_snapshot(
            "2026-08-24", [{"account_id": "sbi_sec", "balance": 95, "source": "manual"}], path=path
        )
        assert get_previous_balance("sbi_sec", path=path) == 95

    def test_before_date_excludes_same_or_later(self, tmp_path):
        path = tmp_path / "s.json"
        append_snapshot(
            "2026-08-24", [{"account_id": "sbi_sec", "balance": 95, "source": "manual"}], path=path
        )
        append_snapshot(
            "2026-08-31", [{"account_id": "sbi_sec", "balance": 100, "source": "manual"}], path=path
        )
        assert get_previous_balance("sbi_sec", before_date="2026-08-31", path=path) == 95


class TestListAndLatest:
    def test_list_snapshot_dates_sorted_unique(self, tmp_path):
        path = tmp_path / "s.json"
        append_snapshot(
            "2026-08-31", [{"account_id": "a", "balance": 1, "source": "manual"}], path=path
        )
        append_snapshot(
            "2026-08-24", [{"account_id": "b", "balance": 1, "source": "manual"}], path=path
        )
        assert list_snapshot_dates(path) == ["2026-08-24", "2026-08-31"]

    def test_latest_snapshot_date(self, tmp_path):
        path = tmp_path / "s.json"
        append_snapshot(
            "2026-08-24", [{"account_id": "a", "balance": 1, "source": "manual"}], path=path
        )
        append_snapshot(
            "2026-08-31", [{"account_id": "a", "balance": 1, "source": "manual"}], path=path
        )
        assert latest_snapshot_date(path) == "2026-08-31"

    def test_latest_snapshot_date_empty(self, tmp_path):
        path = tmp_path / "empty.json"
        assert latest_snapshot_date(path) is None
