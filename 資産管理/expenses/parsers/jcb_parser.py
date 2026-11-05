"""JCBカード(MyJCB) 利用明細CSVパーサー。

実データで確認した実際のヘッダーは:
  ご利用者,カテゴリ,ご利用日,ご利用先など,ご利用金額(￥),支払区分,今回回数,
  訂正サイン,お支払い金額(￥),国内／海外,摘要,備考
このヘッダー行の前に「今回のお支払日」「今回のお支払金額合計」等のサマリー行と
「【ご利用明細】」という見出し行が付くため、base.parse_generic のヘッダー行探索
（find_header_line_index）で対応している。全フィールドがダブルクォートで囲まれた
CSVだが、標準の csv モジュールでそのまま解釈できる。
"""

import csv
from pathlib import Path

from expenses.parsers.base import (
    HEADER_SEARCH_LIMIT,
    CsvFormatError,
    RawTransaction,
    parse_amount,
    parse_generic,
    read_text_with_fallback,
)

ISSUER_ID = "jcb"

DATE_COL_CANDIDATES = ("ご利用日", "利用日", "お取引日")
DESC_COL_CANDIDATES = ("ご利用先など", "利用先名称", "ご利用先", "利用先", "摘要")
AMOUNT_COL_CANDIDATES = ("ご利用金額(￥)", "利用金額", "ご利用金額", "支払金額")

BILLING_TOTAL_LABEL = "今回のお支払金額合計(￥)"


def parse(path: Path) -> list[RawTransaction]:
    return parse_generic(
        path,
        ISSUER_ID,
        DATE_COL_CANDIDATES,
        DESC_COL_CANDIDATES,
        AMOUNT_COL_CANDIDATES,
    )


def extract_billing_total(path: Path) -> int | None:
    """冒頭のサマリー行「"今回のお支払金額合計(￥)","10,975"」から請求額合計を抽出する。"""
    text = read_text_with_fallback(path)
    for line in text.splitlines()[:HEADER_SEARCH_LIMIT]:
        try:
            row = next(csv.reader([line]))
        except StopIteration:
            continue
        for i, cell in enumerate(row):
            if cell.strip() == BILLING_TOTAL_LABEL and i + 1 < len(row):
                try:
                    return parse_amount(row[i + 1])
                except CsvFormatError:
                    return None
    return None
