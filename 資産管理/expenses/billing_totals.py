"""expenses/incoming/{issuer}/ に置かれたカード明細CSVから、今回の請求額合計を抽出し
対応する負債口座（三井住友カード等）の残高候補として使う。

取込（expenses/importer.run_import）で incoming → processed へ移動される前に読む必要があるため、
main.py の commit フローでは run_import() より先にこれを呼び出す。
"""

from pathlib import Path

from expenses.parsers.registry import (
    ISSUER_IDS,
    ISSUER_TO_ACCOUNT_ID,
    extract_billing_total_for_issuer,
)

INCOMING_DIR = Path(__file__).parent / "incoming"


def fetch_card_billing_totals(incoming_dir: Path = INCOMING_DIR) -> dict[str, float]:
    """incoming/{issuer}/ のCSVから請求額合計を抽出し、{account_id: 金額} を返す。

    1issuerに複数CSVがある場合は最初に抽出できたものを使う（通常は1枚のはず）。
    抽出できない・ファイルが無いissuerはキーに含めない（呼び出し側で手動入力にフォールバックする）。
    """
    totals: dict[str, float] = {}
    for issuer_id in ISSUER_IDS:
        account_id = ISSUER_TO_ACCOUNT_ID.get(issuer_id)
        if account_id is None:
            continue
        issuer_dir = incoming_dir / issuer_id
        if not issuer_dir.exists():
            continue
        for csv_path in sorted(issuer_dir.glob("*.csv")):
            total = extract_billing_total_for_issuer(issuer_id, csv_path)
            if total is not None:
                totals[account_id] = float(total)
                break
    return totals
