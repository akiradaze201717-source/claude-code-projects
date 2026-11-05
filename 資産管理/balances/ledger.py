"""残高スナップショット台帳（data/balance_snapshots.json）の読み書き。

株/ir_digest の buyback_events_archive.json と同じ「dictでキー重複解消 →
sorted list で書き戻し」パターンを踏襲した追記型台帳。
キーは (date, account_id) — 同日同口座の再コミットは上書きになる（冪等）。
"""

import json
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
LEDGER_PATH = DATA_DIR / "balance_snapshots.json"


def load_snapshots(path: Path = LEDGER_PATH) -> list[dict]:
    """台帳全件を日付昇順で返す。ファイルが無ければ空リスト。"""
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return sorted(raw, key=lambda e: (e["date"], e["account_id"]))


def append_snapshot(date_str: str, entries: list[dict], path: Path = LEDGER_PATH) -> None:
    """entries: [{"account_id","balance","source","note"}, ...] を date_str のスナップショットとして台帳へマージ保存する。

    同じ (date, account_id) が既にあれば上書き。
    """
    archive: dict[tuple, dict] = {}
    if path.exists():
        for e in json.loads(path.read_text(encoding="utf-8")):
            archive[(e["date"], e["account_id"])] = e

    committed_at = datetime.now().astimezone().isoformat()
    for entry in entries:
        record = {
            "date": date_str,
            "account_id": entry["account_id"],
            "balance": entry["balance"],
            "source": entry.get("source", "manual"),
            "note": entry.get("note", ""),
            "committed_at": committed_at,
        }
        archive[(date_str, entry["account_id"])] = record

    merged = sorted(archive.values(), key=lambda e: (e["date"], e["account_id"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")


def latest_snapshot_date(path: Path = LEDGER_PATH) -> str | None:
    """台帳に記録済みの最新スナップショット日付を返す（無ければ None）。"""
    snapshots = load_snapshots(path)
    if not snapshots:
        return None
    return snapshots[-1]["date"]


def get_balances_for_date(date_str: str, path: Path = LEDGER_PATH) -> dict[str, dict]:
    """指定日のスナップショットを account_id をキーにした辞書で返す。"""
    return {e["account_id"]: e for e in load_snapshots(path) if e["date"] == date_str}


def get_previous_balance(
    account_id: str, before_date: str | None = None, path: Path = LEDGER_PATH
) -> float | None:
    """指定口座の直近の確定残高を返す（無ければ None）。

    before_date を指定すると、その日付より前の最新値を返す（今回未確定分を除外するため）。
    """
    snapshots = [e for e in load_snapshots(path) if e["account_id"] == account_id]
    if before_date is not None:
        snapshots = [e for e in snapshots if e["date"] < before_date]
    if not snapshots:
        return None
    return snapshots[-1]["balance"]


def list_snapshot_dates(path: Path = LEDGER_PATH) -> list[str]:
    """台帳に存在する確定済みスナップショット日付の一覧（昇順・重複なし）。"""
    return sorted({e["date"] for e in load_snapshots(path)})
