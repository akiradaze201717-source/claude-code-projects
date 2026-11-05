"""expenses/importer.py のユニットテスト。

INCOMING_DIR / PROCESSED_DIR は tmp_path に monkeypatch する（実行時にグローバル参照
されるため反映される）。append_transactions は実ファイルI/Oを避けるため patch する。
"""

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import expenses.importer as importer_mod
from expenses.importer import run_import


def _setup_incoming(tmp_path, issuer, filename, content):
    d = tmp_path / "incoming" / issuer
    d.mkdir(parents=True, exist_ok=True)
    (d / filename).write_text(content, encoding="cp932")


class TestRunImport:
    def _patch_dirs(self, monkeypatch, tmp_path):
        monkeypatch.setattr(importer_mod, "INCOMING_DIR", tmp_path / "incoming")
        monkeypatch.setattr(importer_mod, "PROCESSED_DIR", tmp_path / "processed")

    def test_no_incoming_files_returns_zero(self, tmp_path, monkeypatch):
        self._patch_dirs(monkeypatch, tmp_path)
        with patch.object(importer_mod, "append_transactions", return_value=0):
            summary = run_import()
        assert summary.imported_count == 0
        assert summary.skipped_duplicate_count == 0

    def test_valid_csv_imported_and_moved(self, tmp_path, monkeypatch):
        self._patch_dirs(monkeypatch, tmp_path)
        _setup_incoming(
            tmp_path,
            "smbc",
            "meisai.csv",
            "ご利用日,ご利用先,ご利用金額\n2026/08/15,セブン-イレブン,3200\n",
        )

        with patch.object(importer_mod, "append_transactions", return_value=1) as mock_append:
            summary = run_import()

        assert summary.imported_count == 1
        assert summary.skipped_duplicate_count == 0
        mock_append.assert_called_once()
        records = mock_append.call_args[0][0]
        assert records[0]["category"] == "食費"

        # 元のincomingから消え、processedへ移動している
        assert not (tmp_path / "incoming" / "smbc" / "meisai.csv").exists()
        assert (tmp_path / "processed" / "smbc" / "meisai.csv").exists()

    def test_duplicate_skip_counted(self, tmp_path, monkeypatch):
        self._patch_dirs(monkeypatch, tmp_path)
        _setup_incoming(
            tmp_path,
            "jcb",
            "meisai.csv",
            "利用日,利用先名称,利用金額\n2026/08/15,テスト店,1000\n2026/08/16,テスト店2,2000\n",
        )

        with patch.object(importer_mod, "append_transactions", return_value=1):
            summary = run_import()

        assert summary.imported_count == 1
        assert summary.skipped_duplicate_count == 1

    def test_uncategorized_counted(self, tmp_path, monkeypatch):
        self._patch_dirs(monkeypatch, tmp_path)
        _setup_incoming(
            tmp_path, "saison", "meisai.csv", "利用日,利用先,利用金額\n2026/08/15,謎の店,500\n"
        )

        with patch.object(importer_mod, "append_transactions", return_value=1):
            summary = run_import()

        assert summary.uncategorized_count == 1

    def test_malformed_csv_recorded_as_failed(self, tmp_path, monkeypatch):
        # smbcはヘッダー行を前提としない固定列順パーサーのため、ヘッダー行探索で
        # 失敗しうる jcb（parse_generic経由）で「該当ヘッダーが見つからない」ケースを検証する。
        self._patch_dirs(monkeypatch, tmp_path)
        _setup_incoming(tmp_path, "jcb", "broken.csv", "no,matching,headers\n1,2,3\n")

        with patch.object(importer_mod, "append_transactions", return_value=0):
            summary = run_import()

        assert len(summary.failed_files) == 1
        # 解析失敗ファイルはincomingに残る（processedへ動かさない）
        assert (tmp_path / "incoming" / "jcb" / "broken.csv").exists()

    def test_smbc_summary_only_file_yields_zero_transactions_without_error(
        self, tmp_path, monkeypatch
    ):
        """smbcは固定列順パーサーのためヘッダー欠如では例外にならず、単に0件になる。"""
        self._patch_dirs(monkeypatch, tmp_path)
        _setup_incoming(
            tmp_path, "smbc", "summary_only.csv", "テスト　太郎　様,カード番号,カード名称,,,,\n"
        )

        with patch.object(importer_mod, "append_transactions", return_value=0) as mock_append:
            summary = run_import()

        assert summary.imported_count == 0
        assert summary.failed_files == []
        mock_append.assert_called_once_with([])
        assert (tmp_path / "processed" / "smbc" / "summary_only.csv").exists()

    def test_missing_issuer_incoming_dir_skipped_gracefully(self, tmp_path, monkeypatch):
        self._patch_dirs(monkeypatch, tmp_path)
        # incoming/smbc, saison, jcb のいずれも作らない
        with patch.object(importer_mod, "append_transactions", return_value=0):
            summary = run_import()
        assert summary.imported_count == 0
        assert summary.failed_files == []
