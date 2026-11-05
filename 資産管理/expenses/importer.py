"""expenses/incoming/{issuer}/ のCSVを取込み、分類してtransactions.jsonへ追記する。

取込済みCSVは expenses/processed/{issuer}/ へ移動する。
"""

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from expenses.category_rules import UNCATEGORIZED, classify, load_rules
from expenses.ledger import append_transactions, to_ledger_record
from expenses.parsers.base import CsvFormatError
from expenses.parsers.registry import ISSUER_IDS, parse_for_issuer

log = logging.getLogger(__name__)

EXPENSES_DIR = Path(__file__).parent
INCOMING_DIR = EXPENSES_DIR / "incoming"
PROCESSED_DIR = EXPENSES_DIR / "processed"


@dataclass(frozen=True)
class ImportSummary:
    imported_count: int
    skipped_duplicate_count: int
    uncategorized_count: int
    failed_files: list[str]


def run_import() -> ImportSummary:
    rules = load_rules()
    total_seen = 0
    total_added = 0
    total_uncategorized = 0
    failed_files: list[str] = []

    for issuer_id in ISSUER_IDS:
        issuer_incoming = INCOMING_DIR / issuer_id
        issuer_processed = PROCESSED_DIR / issuer_id
        issuer_processed.mkdir(parents=True, exist_ok=True)
        if not issuer_incoming.exists():
            continue

        for csv_path in sorted(issuer_incoming.glob("*.csv")):
            try:
                raw_transactions = parse_for_issuer(issuer_id, csv_path)
            except CsvFormatError as e:
                log.error("CSV解析失敗 (%s): %s", csv_path, e)
                failed_files.append(str(csv_path))
                continue

            records = []
            for txn in raw_transactions:
                category = classify(txn.description, rules)
                if category == UNCATEGORIZED:
                    total_uncategorized += 1
                records.append(to_ledger_record(txn, category))

            total_seen += len(records)
            added = append_transactions(records)
            total_added += added
            log.info(
                "%s: %d件中%d件を新規取込(%d件は重複スキップ)",
                csv_path.name,
                len(records),
                added,
                len(records) - added,
            )

            dest = issuer_processed / csv_path.name
            shutil.move(str(csv_path), str(dest))

    return ImportSummary(
        imported_count=total_added,
        skipped_duplicate_count=total_seen - total_added,
        uncategorized_count=total_uncategorized,
        failed_files=failed_files,
    )
