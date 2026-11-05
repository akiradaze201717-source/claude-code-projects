"""balances/template_builder.py（Excel版）のユニットテスト。

tb.TEMPLATE_PATH をmonkeypatchしてtmp_pathに差し替える
（各関数は基本的にpath引数を明示的に取るが、build_weekly_template内部の保存先だけ
 TEMPLATE_PATHグローバル参照のため、こちらを差し替える）。
get_previous_balance は関数として patch し、実ファイルの残高台帳には依存しない。
"""

import os
import sys
from unittest.mock import patch

import openpyxl
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import balances.template_builder as tb
from balances.accounts import Account
from balances.template_builder import (
    archive_and_reset,
    build_weekly_template,
    fill_auto_values,
    missing_manual_accounts,
    read_target_date,
    read_template_entries,
    to_dashed_date,
)

ACCOUNTS = [
    Account("gmo_coin_jpy", "GMOコイン(現金)", "asset", "暗号資産取引所", "auto_gmo"),
    Account(
        "gmo_coin_crypto", "GMOコイン(暗号資産評価額)", "asset", "暗号資産取引所", "auto_gmo_crypto"
    ),
    Account("sbi_sec", "SBI証券", "asset", "証券", "manual"),
    Account("smbc_card", "三井住友カード", "liability", "クレジットカード", "auto_card_csv"),
]


def _build(tmp_path, monkeypatch, gmo_jpy=None, gmo_crypto=None, raw_date="20260831"):
    monkeypatch.setattr(tb, "TEMPLATE_PATH", tmp_path / "残高入力.xlsx")
    with patch("balances.template_builder.get_previous_balance", return_value=None):
        return build_weekly_template(raw_date, ACCOUNTS, gmo_jpy, gmo_crypto)


def _cell_map(path):
    """口座名 -> (区分, 前回残高, 今回残高, メモ) の辞書。"""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    result = {}
    for row_idx in range(tb.DATA_START_ROW, ws.max_row + 1):
        name = ws.cell(row=row_idx, column=tb.COL_NAME).value
        if not name:
            continue
        result[name] = (
            ws.cell(row=row_idx, column=tb.COL_TYPE).value,
            ws.cell(row=row_idx, column=tb.COL_PREV).value,
            ws.cell(row=row_idx, column=tb.COL_CURRENT).value,
            ws.cell(row=row_idx, column=tb.COL_NOTE).value,
        )
    return result


class TestToDashedDate:
    def test_converts_correctly(self):
        assert to_dashed_date("20260831") == "2026-08-31"


class TestBuildWeeklyTemplate:
    def test_target_date_written(self, tmp_path, monkeypatch):
        path = _build(tmp_path, monkeypatch)
        assert read_target_date(path) == "2026-08-31"

    def test_gmo_auto_values_filled_in(self, tmp_path, monkeypatch):
        path = _build(tmp_path, monkeypatch, gmo_jpy=152340.0, gmo_crypto=300000.0)
        cells = _cell_map(path)
        assert cells["GMOコイン(現金)"][2] == 152340.0
        assert "自動取得値" in cells["GMOコイン(現金)"][3]
        assert cells["GMOコイン(暗号資産評価額)"][2] == 300000.0

    def test_gmo_fetch_failure_leaves_blank_with_note(self, tmp_path, monkeypatch):
        path = _build(tmp_path, monkeypatch, gmo_jpy=None, gmo_crypto=None)
        cells = _cell_map(path)
        assert cells["GMOコイン(現金)"][2] is None
        assert "自動取得失敗" in cells["GMOコイン(現金)"][3]

    def test_manual_account_current_balance_starts_blank(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tb, "TEMPLATE_PATH", tmp_path / "残高入力.xlsx")
        with patch("balances.template_builder.get_previous_balance", return_value=1000000.0):
            path = build_weekly_template("20260831", ACCOUNTS, 100.0, 100.0)
        cells = _cell_map(path)
        assert cells["SBI証券"][2] is None
        assert cells["SBI証券"][1] == 1000000.0

    def test_liability_note_mentions_positive_amount(self, tmp_path, monkeypatch):
        path = _build(tmp_path, monkeypatch, gmo_jpy=100.0, gmo_crypto=100.0)
        cells = _cell_map(path)
        assert "正の数" in cells["三井住友カード"][3]

    def test_regenerating_carries_forward_partial_manual_input(self, tmp_path, monkeypatch):
        path = _build(tmp_path, monkeypatch)

        wb = openpyxl.load_workbook(path)
        ws = wb.active
        for row_idx in range(tb.DATA_START_ROW, ws.max_row + 1):
            if ws.cell(row=row_idx, column=tb.COL_NAME).value == "SBI証券":
                ws.cell(row=row_idx, column=tb.COL_CURRENT, value=1234567)
        wb.save(path)

        path2 = _build(tmp_path, monkeypatch)
        cells = _cell_map(path2)
        assert cells["SBI証券"][2] == 1234567

    def test_type_displayed_in_japanese(self, tmp_path, monkeypatch):
        path = _build(tmp_path, monkeypatch)
        cells = _cell_map(path)
        assert cells["SBI証券"][0] == "資産"
        assert cells["三井住友カード"][0] == "負債"


class TestMissingManualAccounts:
    def test_reports_blank_rows_by_name(self, tmp_path, monkeypatch):
        path = _build(tmp_path, monkeypatch, gmo_jpy=100.0, gmo_crypto=100.0)
        missing = missing_manual_accounts(path, ACCOUNTS)
        assert "SBI証券" in missing
        assert "三井住友カード" in missing

    def test_no_missing_when_all_filled(self, tmp_path, monkeypatch):
        path = _build(tmp_path, monkeypatch, gmo_jpy=100.0, gmo_crypto=100.0)
        wb = openpyxl.load_workbook(path)
        ws = wb.active
        for row_idx in range(tb.DATA_START_ROW, ws.max_row + 1):
            if ws.cell(row=row_idx, column=tb.COL_CURRENT).value in (None, ""):
                ws.cell(row=row_idx, column=tb.COL_CURRENT, value=1000)
        wb.save(path)
        assert missing_manual_accounts(path, ACCOUNTS) == []


class TestReadTemplateEntries:
    def test_source_reflects_account_master(self, tmp_path, monkeypatch):
        path = _build(tmp_path, monkeypatch, gmo_jpy=152340.0, gmo_crypto=300000.0)
        wb = openpyxl.load_workbook(path)
        ws = wb.active
        for row_idx in range(tb.DATA_START_ROW, ws.max_row + 1):
            if ws.cell(row=row_idx, column=tb.COL_NAME).value == "SBI証券":
                ws.cell(row=row_idx, column=tb.COL_CURRENT, value=1000000)
        wb.save(path)

        entries = read_template_entries(path, ACCOUNTS)
        by_id = {e["account_id"]: e for e in entries}
        assert by_id["gmo_coin_jpy"]["source"] == "auto_gmo"
        assert by_id["gmo_coin_crypto"]["source"] == "auto_gmo_crypto"
        assert by_id["sbi_sec"]["source"] == "manual"
        assert by_id["sbi_sec"]["balance"] == 1000000.0

    def test_blank_current_balance_excluded(self, tmp_path, monkeypatch):
        path = _build(tmp_path, monkeypatch, gmo_jpy=None, gmo_crypto=None)
        assert read_template_entries(path, ACCOUNTS) == []

    def test_unknown_account_name_skipped(self, tmp_path, monkeypatch):
        path = _build(tmp_path, monkeypatch, gmo_jpy=None, gmo_crypto=None)
        wb = openpyxl.load_workbook(path)
        ws = wb.active
        ws.cell(row=ws.max_row + 1, column=tb.COL_NAME, value="謎の口座")
        ws.cell(row=ws.max_row, column=tb.COL_CURRENT, value=500)
        wb.save(path)
        entries = read_template_entries(path, ACCOUNTS)
        assert all(e["account_id"] != "謎の口座" for e in entries)


class TestFillAutoValues:
    def test_blank_row_filled_from_dict(self, tmp_path, monkeypatch):
        path = _build(tmp_path, monkeypatch, gmo_jpy=None, gmo_crypto=None)
        filled = fill_auto_values(path, {"smbc_card": 15338.0}, ACCOUNTS)
        assert filled == 1
        cells = _cell_map(path)
        assert cells["三井住友カード"][2] == 15338.0
        assert "自動取得値(CSV)" in cells["三井住友カード"][3]

    def test_already_filled_row_not_overwritten(self, tmp_path, monkeypatch):
        path = _build(tmp_path, monkeypatch, gmo_jpy=None, gmo_crypto=None)
        wb = openpyxl.load_workbook(path)
        ws = wb.active
        for row_idx in range(tb.DATA_START_ROW, ws.max_row + 1):
            if ws.cell(row=row_idx, column=tb.COL_NAME).value == "三井住友カード":
                ws.cell(row=row_idx, column=tb.COL_CURRENT, value=99999)
        wb.save(path)

        filled = fill_auto_values(path, {"smbc_card": 15338.0}, ACCOUNTS)
        assert filled == 0
        assert _cell_map(path)["三井住友カード"][2] == 99999

    def test_unrelated_account_id_ignored(self, tmp_path, monkeypatch):
        path = _build(tmp_path, monkeypatch, gmo_jpy=None, gmo_crypto=None)
        assert fill_auto_values(path, {"no_such_account": 100.0}, ACCOUNTS) == 0

    def test_empty_auto_values_noop(self, tmp_path, monkeypatch):
        path = _build(tmp_path, monkeypatch, gmo_jpy=None, gmo_crypto=None)
        assert fill_auto_values(path, {}, ACCOUNTS) == 0


class TestArchiveAndReset:
    def test_archived_copy_created(self, tmp_path, monkeypatch):
        path = _build(tmp_path, monkeypatch, gmo_jpy=100.0, gmo_crypto=100.0)
        archived = archive_and_reset(path, "2026-08-31")
        assert archived.name == "残高入力_20260831.xlsx"
        assert archived.exists()

    def test_archived_copy_preserves_values(self, tmp_path, monkeypatch):
        path = _build(tmp_path, monkeypatch, gmo_jpy=152340.0, gmo_crypto=300000.0)
        archived = archive_and_reset(path, "2026-08-31")
        cells = _cell_map(archived)
        assert cells["GMOコイン(現金)"][2] == 152340.0

    def test_live_file_current_balance_reset(self, tmp_path, monkeypatch):
        path = _build(tmp_path, monkeypatch, gmo_jpy=152340.0, gmo_crypto=300000.0)
        archive_and_reset(path, "2026-08-31")
        cells = _cell_map(path)
        assert cells["GMOコイン(現金)"][2] is None
        assert cells["GMOコイン(暗号資産評価額)"][2] is None

    def test_live_file_other_columns_untouched_after_reset(self, tmp_path, monkeypatch):
        path = _build(tmp_path, monkeypatch, gmo_jpy=100.0, gmo_crypto=100.0)
        archive_and_reset(path, "2026-08-31")
        cells = _cell_map(path)
        assert cells["SBI証券"][0] == "資産"  # 区分列は残る


class TestReadTargetDate:
    def test_missing_date_raises(self, tmp_path, monkeypatch):
        path = tmp_path / "empty.xlsx"
        wb = openpyxl.Workbook()
        wb.save(path)
        with pytest.raises(ValueError):
            read_target_date(path)
