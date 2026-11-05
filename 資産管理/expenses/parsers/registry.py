"""issuer名 → パーサーモジュール の対応表。expenses/incoming/{issuer}/ のフォルダ名と一致させる。"""

from pathlib import Path

from expenses.parsers import jcb_parser, saison_parser, smbc_parser
from expenses.parsers.base import RawTransaction

_PARSERS = {
    smbc_parser.ISSUER_ID: smbc_parser.parse,
    saison_parser.ISSUER_ID: saison_parser.parse,
    jcb_parser.ISSUER_ID: jcb_parser.parse,
}

_BILLING_TOTAL_EXTRACTORS = {
    smbc_parser.ISSUER_ID: smbc_parser.extract_billing_total,
    saison_parser.ISSUER_ID: saison_parser.extract_billing_total,
    jcb_parser.ISSUER_ID: jcb_parser.extract_billing_total,
}

ISSUER_IDS = tuple(_PARSERS.keys())

# issuer_id → 対応する資産管理口座ID（balances/accounts.py の accounts.json と対応させる）
ISSUER_TO_ACCOUNT_ID = {
    smbc_parser.ISSUER_ID: "smbc_card",
    saison_parser.ISSUER_ID: "saison_gold",
    jcb_parser.ISSUER_ID: "jcb_card",
}


def parse_for_issuer(issuer_id: str, path: Path) -> list[RawTransaction]:
    parser = _PARSERS.get(issuer_id)
    if parser is None:
        raise ValueError(f"未知のissuer_id: {issuer_id}（対応: {ISSUER_IDS}）")
    return parser(path)


def extract_billing_total_for_issuer(issuer_id: str, path: Path) -> int | None:
    """issuerのCSVから今回の請求額合計を抽出する。抽出ロジック未対応のissuerはNone。"""
    extractor = _BILLING_TOTAL_EXTRACTORS.get(issuer_id)
    if extractor is None:
        return None
    return extractor(path)
