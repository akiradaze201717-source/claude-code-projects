"""支出取引明細台帳（data/transactions.json）の読み書き・重複判定。

同一取引（issuer|date|amount|description のハッシュ）の重複取込を防ぐ。
過去分を含むCSVを再ダウンロード・再取込しても重複追加されない。
"""

import hashlib
import json
from datetime import date, datetime
from pathlib import Path

from expenses.parsers.base import RawTransaction

DATA_DIR = Path(__file__).parent.parent / "data"
TRANSACTIONS_PATH = DATA_DIR / "transactions.json"


def transaction_hash(issuer: str, txn_date: date, amount: int, description: str) -> str:
    text = f"{issuer}|{txn_date.isoformat()}|{amount}|{description}"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def load_transactions(path: Path = TRANSACTIONS_PATH) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def existing_hashes(path: Path = TRANSACTIONS_PATH) -> set[str]:
    return {t["hash"] for t in load_transactions(path)}


def append_transactions(new_records: list[dict], path: Path = TRANSACTIONS_PATH) -> int:
    """new_records（hashキー含む）を台帳へ追記。重複hashはスキップ。実際に追加した件数を返す。"""
    existing = load_transactions(path)
    seen = {t["hash"] for t in existing}

    added = 0
    for record in new_records:
        if record["hash"] in seen:
            continue
        existing.append(record)
        seen.add(record["hash"])
        added += 1

    existing.sort(key=lambda t: (t["txn_date"], t["hash"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    return added


def to_ledger_record(txn: RawTransaction, category: str) -> dict:
    return {
        "hash": transaction_hash(txn.issuer, txn.txn_date, txn.amount, txn.description),
        "issuer": txn.issuer,
        "txn_date": txn.txn_date.isoformat(),
        "amount": txn.amount,
        "description": txn.description,
        "category": category,
        "source_file": txn.source_file,
        "imported_at": datetime.now().astimezone().isoformat(),
    }
