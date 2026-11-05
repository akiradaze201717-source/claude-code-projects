"""カード明細CSVパーサーの共通型。

三井住友カード・セゾンゴールドカード・JCBカードの実際のCSVで確認したところ、
いずれも「今回のご請求額」等のサマリー行が本来のヘッダー行の前に数行付く形式だった
（単純な1行目=ヘッダーではない）。そのため列名候補は「先頭一致」ではなく、
ファイル冒頭数行の中からヘッダー行を探索する方式にしている。
三井住友カードのみヘッダー行自体が無い完全な固定列順のため smbc_parser.py で別途対応する。
"""

import csv
import io
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class RawTransaction:
    txn_date: date
    amount: int  # 円。返金等はマイナスも許容
    description: str
    issuer: str  # "smbc" / "saison" / "jcb"
    source_file: str


class IssuerParser(Protocol):
    issuer_id: str

    def parse(self, path: Path) -> list[RawTransaction]: ...


class CsvFormatError(Exception):
    """CSVの列構成が想定と一致せず解釈できない。"""


# 日本のカード会社CSVはほぼ Shift-JIS(CP932)。UTF-8化されているケースにもフォールバックする。
_ENCODING_CANDIDATES = ("cp932", "utf-8-sig", "utf-8")


def read_text_with_fallback(path: Path) -> str:
    last_error: Exception | None = None
    for enc in _ENCODING_CANDIDATES:
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError as e:
            last_error = e
            continue
    raise CsvFormatError(f"文字コード判定失敗: {path}") from last_error


def resolve_column(fieldnames: list[str], candidates: tuple[str, ...]) -> str:
    """fieldnames の中から candidates の先頭一致で実際の列名を1つ返す。"""
    for candidate in candidates:
        if candidate in fieldnames:
            return candidate
    raise CsvFormatError(f"該当する列が見つかりません。候補={candidates} 実際の列={fieldnames}")


def dict_reader_from_text(text: str) -> csv.DictReader:
    return csv.DictReader(io.StringIO(text))


# ヘッダー行探索はファイル冒頭のサマリー行に惑わされないよう、この行数までに限定する。
HEADER_SEARCH_LIMIT = 30


def find_header_line_index(
    text: str,
    date_candidates: tuple[str, ...],
    desc_candidates: tuple[str, ...],
    amount_candidates: tuple[str, ...],
) -> int | None:
    """date/desc/amount の候補列名が全て揃う行を探し、その行番号（0始まり）を返す。

    セゾン・JCBのように「今回のご請求額」等のサマリー行がヘッダーより前に付く
    実際のCSV形式に対応するため。見つからなければ None。
    """
    lines = text.splitlines()
    for i, line in enumerate(lines[:HEADER_SEARCH_LIMIT]):
        try:
            row = next(csv.reader([line]))
        except StopIteration:
            continue
        if (
            any(c in row for c in date_candidates)
            and any(c in row for c in desc_candidates)
            and any(c in row for c in amount_candidates)
        ):
            return i
    return None


def parse_amount(raw: str) -> int:
    """ "1,234円" や "-1,234" のような表記から整数円を取り出す。"""
    cleaned = raw.strip().replace(",", "").replace("円", "").replace("¥", "")
    if not cleaned:
        raise CsvFormatError(f"金額が空です: {raw!r}")
    return int(float(cleaned))


def parse_date_flexible(raw: str) -> date:
    """ "2026/08/15" "2026-08-15" "20260815" のいずれにも対応する日付パース。"""
    cleaned = raw.strip()
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y%m%d", "%Y年%m月%d日"):
        try:
            from datetime import datetime

            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    raise CsvFormatError(f"日付として解釈できません: {raw!r}")


def parse_generic(
    path: Path,
    issuer_id: str,
    date_col_candidates: tuple[str, ...],
    desc_col_candidates: tuple[str, ...],
    amount_col_candidates: tuple[str, ...],
) -> list[RawTransaction]:
    """列名候補リストに基づく汎用CSVパース処理。3イシュアのパーサーから共通利用する。

    「今回のご請求額」等のサマリー行がヘッダーより前に付くファイルに対応するため、
    1行目を無条件にヘッダーとはみなさず、冒頭数行の中からヘッダー行を探索する。
    金額・日付として解釈できない行はスキップする（明細以外の合計行・注記行対策）。
    """
    text = read_text_with_fallback(path)
    header_idx = find_header_line_index(
        text, date_col_candidates, desc_col_candidates, amount_col_candidates
    )
    if header_idx is None:
        raise CsvFormatError(
            f"ヘッダー行が見つかりません（冒頭{HEADER_SEARCH_LIMIT}行を探索）。"
            f"候補: 日付={date_col_candidates} 摘要={desc_col_candidates} 金額={amount_col_candidates}"
        )

    body_text = "\n".join(text.splitlines()[header_idx:])
    reader = dict_reader_from_text(body_text)
    fieldnames = reader.fieldnames or []

    date_col = resolve_column(fieldnames, date_col_candidates)
    desc_col = resolve_column(fieldnames, desc_col_candidates)
    amount_col = resolve_column(fieldnames, amount_col_candidates)

    transactions: list[RawTransaction] = []
    for row in reader:
        raw_date = (row.get(date_col) or "").strip()
        raw_amount = (row.get(amount_col) or "").strip()
        raw_desc = (row.get(desc_col) or "").strip()
        if not raw_date or not raw_amount:
            continue
        try:
            txn_date = parse_date_flexible(raw_date)
            amount = parse_amount(raw_amount)
        except CsvFormatError:
            continue
        transactions.append(
            RawTransaction(
                txn_date=txn_date,
                amount=amount,
                description=raw_desc,
                issuer=issuer_id,
                source_file=path.name,
            )
        )
    return transactions
