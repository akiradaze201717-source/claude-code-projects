"""expenses/parsers/base.py の共通ロジックのユニットテスト。

CP932/UTF-8のフォールバック・金額パース・日付パース・列名候補解決を検証する。
実データのCSV列名は未入手のため、フィクスチャは各テスト内で動的に生成する
（静的バイナリファイルのエンコーディング崩れを避けるため）。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from expenses.parsers.base import (
    CsvFormatError,
    find_header_line_index,
    parse_amount,
    parse_date_flexible,
    parse_generic,
    read_text_with_fallback,
    resolve_column,
)


class TestReadTextWithFallback:
    def test_cp932_file_decoded(self, tmp_path):
        path = tmp_path / "cp932.csv"
        path.write_text("ご利用日,ご利用先,ご利用金額\n", encoding="cp932")
        text = read_text_with_fallback(path)
        assert "ご利用日" in text

    def test_utf8_sig_file_decoded(self, tmp_path):
        path = tmp_path / "utf8sig.csv"
        path.write_text("利用日,利用先,利用金額\n", encoding="utf-8-sig")
        text = read_text_with_fallback(path)
        assert "利用日" in text

    def test_plain_utf8_file_decoded(self, tmp_path):
        path = tmp_path / "utf8.csv"
        path.write_text("date,desc,amount\n", encoding="utf-8")
        text = read_text_with_fallback(path)
        assert "date" in text


class TestResolveColumn:
    def test_first_matching_candidate_used(self):
        assert resolve_column(["利用日", "利用先"], ("ご利用日", "利用日")) == "利用日"

    def test_no_match_raises(self):
        with pytest.raises(CsvFormatError):
            resolve_column(["foo", "bar"], ("ご利用日", "利用日"))


class TestParseAmount:
    def test_plain_number(self):
        assert parse_amount("1234") == 1234

    def test_comma_separated(self):
        assert parse_amount("1,234,567") == 1234567

    def test_yen_symbol(self):
        assert parse_amount("¥3,200") == 3200

    def test_yen_kanji_suffix(self):
        assert parse_amount("3200円") == 3200

    def test_negative_amount(self):
        assert parse_amount("-500") == -500

    def test_empty_raises(self):
        with pytest.raises(CsvFormatError):
            parse_amount("")


class TestParseDateFlexible:
    def test_slash_format(self):
        assert parse_date_flexible("2026/08/15").isoformat() == "2026-08-15"

    def test_dash_format(self):
        assert parse_date_flexible("2026-08-15").isoformat() == "2026-08-15"

    def test_compact_format(self):
        assert parse_date_flexible("20260815").isoformat() == "2026-08-15"

    def test_kanji_format(self):
        assert parse_date_flexible("2026年08月15日").isoformat() == "2026-08-15"

    def test_invalid_raises(self):
        with pytest.raises(CsvFormatError):
            parse_date_flexible("not-a-date")


class TestParseGeneric:
    def test_basic_rows_parsed(self, tmp_path):
        path = tmp_path / "sample.csv"
        path.write_text(
            "ご利用日,ご利用先,ご利用金額\n"
            "2026/08/15,セブン-イレブン,3200\n"
            "2026/08/16,スターバックス,650\n",
            encoding="utf-8",
        )
        txns = parse_generic(
            path,
            "smbc",
            ("ご利用日", "利用日"),
            ("ご利用先", "利用先"),
            ("ご利用金額", "利用金額"),
        )
        assert len(txns) == 2
        assert txns[0].amount == 3200
        assert txns[0].description == "セブン-イレブン"
        assert txns[0].issuer == "smbc"
        assert txns[0].source_file == "sample.csv"

    def test_rows_with_unparseable_date_skipped(self, tmp_path):
        path = tmp_path / "sample.csv"
        path.write_text(
            "ご利用日,ご利用先,ご利用金額\n合計,,3850\n2026/08/15,セブン-イレブン,3200\n",
            encoding="utf-8",
        )
        txns = parse_generic(
            path,
            "smbc",
            ("ご利用日",),
            ("ご利用先",),
            ("ご利用金額",),
        )
        assert len(txns) == 1

    def test_missing_header_raises(self, tmp_path):
        path = tmp_path / "sample.csv"
        path.write_text("date,desc,amount\n2026/08/15,foo,100\n", encoding="utf-8")
        with pytest.raises(CsvFormatError):
            parse_generic(path, "smbc", ("ご利用日",), ("ご利用先",), ("ご利用金額",))

    def test_no_header_row_raises(self, tmp_path):
        path = tmp_path / "empty.csv"
        path.write_text("", encoding="utf-8")
        with pytest.raises(CsvFormatError):
            parse_generic(path, "smbc", ("ご利用日",), ("ご利用先",), ("ご利用金額",))

    def test_header_after_summary_preamble(self, tmp_path):
        """セゾン・JCB実データと同じ形式: サマリー行の後にヘッダー行が来る。"""
        path = tmp_path / "sample.csv"
        path.write_text(
            "カード名称,テストゴールドカード\n"
            "お支払日,2026/09/04\n"
            "今回ご請求額,0000008524\n"
            "\n"
            "利用日,ご利用店名及び商品名,利用金額,備考\n"
            "2026/07/01,セブンイレブン,352,\n",
            encoding="utf-8",
        )
        txns = parse_generic(
            path,
            "saison",
            ("利用日",),
            ("ご利用店名及び商品名",),
            ("利用金額",),
        )
        assert len(txns) == 1
        assert txns[0].description == "セブンイレブン"
        assert txns[0].amount == 352


class TestFindHeaderLineIndex:
    def test_header_at_first_line(self):
        text = "ご利用日,ご利用先,ご利用金額\n2026/08/15,foo,100\n"
        idx = find_header_line_index(text, ("ご利用日",), ("ご利用先",), ("ご利用金額",))
        assert idx == 0

    def test_header_after_preamble(self):
        text = "サマリー,情報\n\n利用日,利用先,利用金額\n2026/08/15,foo,100\n"
        idx = find_header_line_index(text, ("利用日",), ("利用先",), ("利用金額",))
        assert idx == 2

    def test_not_found_returns_none(self):
        text = "date,desc,amount\n2026/08/15,foo,100\n"
        idx = find_header_line_index(text, ("ご利用日",), ("ご利用先",), ("ご利用金額",))
        assert idx is None
