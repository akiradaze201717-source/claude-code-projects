"""balances/commit.py のユニットテスト。

台帳・口座マスタ・テンプレートI/Oへのアクセスはすべて patch し、実データファイルには
一切触れない（テンプレートの実ファイルI/O自体は test_template_builder.py 側で検証する）。
"""

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import balances.commit as commit_mod
from balances.accounts import Account
from balances.commit import IncompleteInputError, NoTemplateFoundError, commit_weekly_snapshot

ACCOUNTS = [
    Account("gmo_coin_jpy", "GMOコイン(現金)", "asset", "暗号資産取引所", "auto_gmo"),
    Account("sbi_sec", "SBI証券", "asset", "証券", "manual"),
    Account("smbc_card", "三井住友カード", "liability", "クレジットカード", "auto_card_csv"),
]
ACCOUNTS_BY_ID = {a.id: a for a in ACCOUNTS}


class TestNoTemplateFound:
    def test_missing_explicit_path_raises(self, tmp_path):
        with pytest.raises(NoTemplateFoundError):
            commit_weekly_snapshot(template_path=tmp_path / "残高入力.xlsx", accounts=ACCOUNTS)

    def test_no_pending_template_at_all_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(commit_mod, "find_latest_pending_template", lambda: None)
        with pytest.raises(NoTemplateFoundError):
            commit_weekly_snapshot(accounts=ACCOUNTS)


class TestIncompleteInput:
    def test_missing_accounts_blocks_commit(self, tmp_path):
        template = tmp_path / "残高入力.xlsx"
        template.write_text("dummy", encoding="utf-8")
        with patch.object(commit_mod, "missing_manual_accounts", return_value=["SBI証券"]):
            with pytest.raises(IncompleteInputError) as exc:
                commit_weekly_snapshot(template_path=template, accounts=ACCOUNTS)
        assert exc.value.missing_accounts == ["SBI証券"]
        # 未入力のためarchive_and_resetは呼ばれず、ライブファイルはそのまま残る
        assert template.exists()


class TestHappyPath:
    def _run(self, tmp_path, monkeypatch, prior_dates, prev_balances_map=None):
        template = tmp_path / "残高入力.xlsx"
        template.write_text("dummy", encoding="utf-8")
        archived_path = tmp_path / "archive" / "残高入力_20260831.xlsx"

        entries = [
            {"account_id": "gmo_coin_jpy", "balance": 100000, "source": "auto_gmo", "note": ""},
            {"account_id": "sbi_sec", "balance": 1000000, "source": "manual", "note": ""},
            {"account_id": "smbc_card", "balance": 30000, "source": "auto_card_csv", "note": ""},
        ]

        def fake_get_balances_for_date(date_str):
            if date_str == "2026-08-31":
                return {e["account_id"]: {**e, "date": date_str} for e in entries}
            return prev_balances_map or {}

        with (
            patch.object(commit_mod, "missing_manual_accounts", return_value=[]),
            patch.object(commit_mod, "read_target_date", return_value="2026-08-31"),
            patch.object(commit_mod, "read_template_entries", return_value=entries),
            patch.object(commit_mod, "list_snapshot_dates", return_value=prior_dates),
            patch.object(
                commit_mod, "get_balances_for_date", side_effect=fake_get_balances_for_date
            ),
            patch.object(commit_mod, "append_snapshot") as mock_append,
            patch.object(
                commit_mod, "archive_and_reset", return_value=archived_path
            ) as mock_archive,
            patch.object(commit_mod, "accounts_by_id", return_value=ACCOUNTS_BY_ID),
        ):
            result = commit_weekly_snapshot(template_path=template, accounts=ACCOUNTS)

        return result, template, archived_path, mock_append, mock_archive

    def test_first_ever_commit_has_no_wow_change(self, tmp_path, monkeypatch):
        result, *_ = self._run(tmp_path, monkeypatch, prior_dates=[])
        assert result.wow_change is None
        assert result.snapshot_date == "2026-08-31"

    def test_networth_computed_correctly(self, tmp_path, monkeypatch):
        result, *_ = self._run(tmp_path, monkeypatch, prior_dates=[])
        assert result.networth.total_assets == 1100000
        assert result.networth.total_liabilities == 30000
        assert result.networth.net_worth == 1070000

    def test_wow_change_with_prior_snapshot(self, tmp_path, monkeypatch):
        prev_balances = {
            "gmo_coin_jpy": {"account_id": "gmo_coin_jpy", "balance": 90000},
            "sbi_sec": {"account_id": "sbi_sec", "balance": 900000},
            "smbc_card": {"account_id": "smbc_card", "balance": 20000},
        }
        result, *_ = self._run(
            tmp_path, monkeypatch, prior_dates=["2026-08-24"], prev_balances_map=prev_balances
        )
        # 前回純資産 = 90000+900000-20000 = 970000, 今回 = 1070000 -> +100000
        assert result.wow_change == 100000

    def test_archive_and_reset_called_and_result_uses_its_path(self, tmp_path, monkeypatch):
        result, template, archived_path, _, mock_archive = self._run(
            tmp_path, monkeypatch, prior_dates=[]
        )
        mock_archive.assert_called_once_with(template, "2026-08-31")
        assert result.template_path == archived_path

    def test_append_snapshot_called_with_parsed_entries(self, tmp_path, monkeypatch):
        _, _, _, mock_append, _ = self._run(tmp_path, monkeypatch, prior_dates=[])
        mock_append.assert_called_once()
        args = mock_append.call_args[0]
        assert args[0] == "2026-08-31"
        assert len(args[1]) == 3
