"""expenses/ledger.py のユニットテスト。"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from expenses.ledger import (
    append_transactions,
    load_transactions,
    to_ledger_record,
    transaction_hash,
)
from expenses.parsers.base import RawTransaction


def _txn(desc="セブン-イレブン", amount=3200, txn_date=date(2026, 8, 15), issuer="smbc"):
    return RawTransaction(
        txn_date=txn_date, amount=amount, description=desc, issuer=issuer, source_file="f.csv"
    )


class TestTransactionHash:
    def test_same_inputs_same_hash(self):
        h1 = transaction_hash("smbc", date(2026, 8, 15), 3200, "セブン-イレブン")
        h2 = transaction_hash("smbc", date(2026, 8, 15), 3200, "セブン-イレブン")
        assert h1 == h2

    def test_different_amount_different_hash(self):
        h1 = transaction_hash("smbc", date(2026, 8, 15), 3200, "セブン-イレブン")
        h2 = transaction_hash("smbc", date(2026, 8, 15), 3201, "セブン-イレブン")
        assert h1 != h2


class TestAppendTransactions:
    def test_new_records_added(self, tmp_path):
        path = tmp_path / "transactions.json"
        record = to_ledger_record(_txn(), "食費")
        added = append_transactions([record], path=path)
        assert added == 1
        assert len(load_transactions(path)) == 1

    def test_duplicate_hash_skipped(self, tmp_path):
        path = tmp_path / "transactions.json"
        record = to_ledger_record(_txn(), "食費")
        append_transactions([record], path=path)
        added_again = append_transactions([record], path=path)
        assert added_again == 0
        assert len(load_transactions(path)) == 1

    def test_different_transactions_both_kept(self, tmp_path):
        path = tmp_path / "transactions.json"
        r1 = to_ledger_record(_txn(desc="セブン-イレブン"), "食費")
        r2 = to_ledger_record(_txn(desc="スターバックス", amount=650), "外食")
        append_transactions([r1, r2], path=path)
        assert len(load_transactions(path)) == 2
