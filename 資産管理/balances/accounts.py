"""口座マスタ（data/accounts.json）の読み込み・検証。"""

import json
from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
ACCOUNTS_PATH = DATA_DIR / "accounts.json"

ASSET = "asset"
LIABILITY = "liability"

SOURCE_AUTO_GMO = "auto_gmo"
SOURCE_AUTO_GMO_CRYPTO = "auto_gmo_crypto"
SOURCE_AUTO_CARD_CSV = "auto_card_csv"
SOURCE_MANUAL = "manual"

# template_builder.build_weekly_template() が「単一の共有値」で自動的に埋められるsource。
# auto_card_csv は口座ごとに異なる値をCSVから抽出する必要があるため、build_weekly_template
# 自体はこれを manual と同様に扱い、後続の template_builder.fill_auto_values() で埋める
# （expenses.billing_totals.fetch_card_billing_totals 経由）。
AUTO_SOURCES = {SOURCE_AUTO_GMO, SOURCE_AUTO_GMO_CRYPTO}


@dataclass(frozen=True)
class Account:
    id: str
    name: str
    type: str  # "asset" | "liability"
    category: str
    source: str  # "auto_gmo" | "auto_gmo_crypto" | "auto_card_csv" | "manual"


def load_accounts(path: Path = ACCOUNTS_PATH) -> list[Account]:
    """口座マスタを読み込み Account のリストを返す。"""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [Account(**item) for item in raw]


def accounts_by_id(path: Path = ACCOUNTS_PATH) -> dict[str, Account]:
    """id をキーにした口座マスタの辞書を返す。"""
    return {a.id: a for a in load_accounts(path)}
