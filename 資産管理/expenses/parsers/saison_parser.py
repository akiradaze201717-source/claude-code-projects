"""セゾンゴールドカード 利用明細CSVパーサー。

実データで確認した実際のヘッダーは:
  利用日,ご利用店名及び商品名,本人・家族区分,支払区分名称,締前入金区分,利用金額,備考
このヘッダー行の前に「カード名称」「お支払日」「今回ご請求額」のサマリー行が付くため、
base.parse_generic のヘッダー行探索（find_header_line_index）で対応している。
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

ISSUER_ID = "saison"

DATE_COL_CANDIDATES = ("利用日", "ご利用日", "お取引日")
DESC_COL_CANDIDATES = ("ご利用店名及び商品名", "利用先", "ご利用先", "加盟店名", "摘要")
AMOUNT_COL_CANDIDATES = ("利用金額", "ご利用金額", "支払金額")

BILLING_TOTAL_LABEL = "今回ご請求額"


def parse(path: Path) -> list[RawTransaction]:
    return parse_generic(
        path,
        ISSUER_ID,
        DATE_COL_CANDIDATES,
        DESC_COL_CANDIDATES,
        AMOUNT_COL_CANDIDATES,
    )


def extract_billing_total(path: Path) -> int | None:
    """冒頭のサマリー行「今回ご請求額,0000008524」から請求額合計を抽出する。"""
    text = read_text_with_fallback(path)
    for line in text.splitlines()[:HEADER_SEARCH_LIMIT]:
        try:
            row = next(csv.reader([line]))
        except StopIteration:
            continue
        if row and row[0].strip() == BILLING_TOTAL_LABEL and len(row) > 1:
            try:
                return parse_amount(row[1])
            except CsvFormatError:
                return None
    return None
