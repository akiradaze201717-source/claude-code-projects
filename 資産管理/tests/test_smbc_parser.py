"""expenses/parsers/smbc_parser.py のユニットテスト。

三井住友カード(Vpass)の実データで確認した形式: ヘッダー行が無く、1行目はカード名義の
サマリー行、2行目以降が固定列順(日付,利用先,金額,回数,回,金額,備考)の明細。
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from expenses.parsers.smbc_parser import extract_billing_total, parse


class TestSmbcParser:
    def test_summary_line_skipped_and_transactions_parsed(self, tmp_path):
        path = tmp_path / "smbc.csv"
        path.write_text(
            "テスト　太郎　様,0000-00**-****-****,三井住友カード,,,,\n"
            "2026/7/26,サンプル食堂,1500,1,1,1500,\n"
            "2026/8/13,サンプル投信積立,10000,1,1,10000,\n",
            encoding="cp932",
        )
        txns = parse(path)
        assert len(txns) == 2
        assert all(t.issuer == "smbc" for t in txns)
        assert txns[0].description == "サンプル食堂"
        assert txns[0].amount == 1500

    def test_unpadded_month_day_date_parsed(self, tmp_path):
        """ "2026/7/26" のような0埋めなし日付も解釈できる。"""
        path = tmp_path / "smbc.csv"
        path.write_text(
            "テスト　太郎　様,カード番号,カード名称,,,,\n2026/7/6,テスト店,500,1,1,500,\n",
            encoding="cp932",
        )
        txns = parse(path)
        assert len(txns) == 1
        assert txns[0].txn_date.isoformat() == "2026-07-06"

    def test_foreign_currency_remark_column_ignored_but_row_parsed(self, tmp_path):
        path = tmp_path / "smbc.csv"
        path.write_text(
            "テスト　太郎　様,カード番号,カード名称,,,,\n"
            "2026/7/17,ANTHROPIC* CLAUDE SUB (ANTHROPIC.COM),3705,1,1,3705,22.00　USD　168.443　07 18\n",
            encoding="cp932",
        )
        txns = parse(path)
        assert len(txns) == 1
        assert txns[0].amount == 3705

    def test_empty_file_returns_no_transactions(self, tmp_path):
        path = tmp_path / "empty.csv"
        path.write_text("", encoding="cp932")
        assert parse(path) == []

    def test_short_rows_ignored(self, tmp_path):
        path = tmp_path / "smbc.csv"
        path.write_text(
            "テスト　太郎　様,カード番号,カード名称,,,,\n\n2026/7/26,サンプル食堂,1500,1,1,1500,\n",
            encoding="cp932",
        )
        txns = parse(path)
        assert len(txns) == 1


class TestExtractBillingTotal:
    def test_total_row_extracted(self, tmp_path):
        path = tmp_path / "smbc.csv"
        path.write_text(
            "テスト　太郎　様,カード番号,カード名称,,,,\n"
            "2026/7/26,サンプル食堂,1500,1,1,1500,\n"
            "2026/8/13,積立サービス,10000,1,1,10000,\n"
            ",,,,,11500,\n",
            encoding="cp932",
        )
        assert extract_billing_total(path) == 11500

    def test_no_total_row_returns_none(self, tmp_path):
        path = tmp_path / "smbc.csv"
        path.write_text(
            "テスト　太郎　様,カード番号,カード名称,,,,\n2026/7/26,サンプル食堂,1500,1,1,1500,\n",
            encoding="cp932",
        )
        assert extract_billing_total(path) is None
