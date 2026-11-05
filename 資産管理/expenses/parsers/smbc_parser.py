"""三井住友カード(Vpass) 利用明細CSVパーサー。

実データで確認したところ、この形式にはヘッダー行が存在しない。1行目はカード名義・
マスク済みカード番号・カード名称のサマリー行で、2行目以降が固定列順の明細:
  列0=利用日(YYYY/M/D), 列1=利用先, 列2=利用金額, 列3=支払回数, 列4=何回目,
  列5=今回請求額(列2と同額のことが多い), 列6=海外利用時の為替情報等（備考）

そのため他2社のような列名候補方式ではなく、列0が日付として解釈できるかどうかで
サマリー行と明細行を判別する（サマリー行は日付ではないため自動的にスキップされる）。
"""

import csv
import io
from pathlib import Path

from expenses.parsers.base import (
    CsvFormatError,
    RawTransaction,
    parse_amount,
    parse_date_flexible,
    read_text_with_fallback,
)

ISSUER_ID = "smbc"

DATE_COL_INDEX = 0
DESC_COL_INDEX = 1
AMOUNT_COL_INDEX = 2


def parse(path: Path) -> list[RawTransaction]:
    text = read_text_with_fallback(path)
    reader = csv.reader(io.StringIO(text))

    transactions: list[RawTransaction] = []
    for row in reader:
        if len(row) <= max(DATE_COL_INDEX, DESC_COL_INDEX, AMOUNT_COL_INDEX):
            continue
        try:
            txn_date = parse_date_flexible(row[DATE_COL_INDEX])
            amount = parse_amount(row[AMOUNT_COL_INDEX])
        except CsvFormatError:
            # 1行目のカード名義サマリー行など、日付/金額として解釈できない行は明細ではないため無視
            continue
        transactions.append(
            RawTransaction(
                txn_date=txn_date,
                amount=amount,
                description=row[DESC_COL_INDEX].strip(),
                issuer=ISSUER_ID,
                source_file=path.name,
            )
        )
    return transactions


TOTAL_COL_INDEX = 5


def extract_billing_total(path: Path) -> int | None:
    """明細末尾の合計行（例: ",,,,,15338,"）から今回の請求額合計を抽出する。

    合計行は日付・利用先の列が空で、支払金額列(index 5)にのみ値がある行と判別する。
    複数該当する場合は最後に見つかった行を採用する（合計行はファイル末尾にあるため）。
    """
    text = read_text_with_fallback(path)
    reader = csv.reader(io.StringIO(text))
    total: int | None = None
    for row in reader:
        if len(row) <= TOTAL_COL_INDEX:
            continue
        if row[DATE_COL_INDEX].strip() or row[DESC_COL_INDEX].strip():
            continue  # 明細行（日付・利用先が入っている）は合計行ではない
        try:
            total = parse_amount(row[TOTAL_COL_INDEX])
        except CsvFormatError:
            continue
    return total
