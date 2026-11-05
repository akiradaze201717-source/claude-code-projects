"""expenses/parsers/saison_parser.py のユニットテスト。

実データで確認した形式: カード名称・お支払日・今回ご請求額のサマリー行 → 空行 →
ヘッダー行(利用日,ご利用店名及び商品名,本人・家族区分,支払区分名称,締前入金区分,利用金額,備考)
→ 明細行、という構成。
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from expenses.parsers.saison_parser import extract_billing_total, parse

SAMPLE = (
    "カード名称,セゾンカード\n"
    "お支払日,2026/09/04\n"
    "今回ご請求額,0000002500\n"
    "\n"
    "利用日,ご利用店名及び商品名,本人・家族区分,支払区分名称,締前入金区分,利用金額,備考\n"
    "2026/07/01,サンプルサブスク,,1回,,1000,\n"
    "2026/07/24,サンプルスタンド,,1回,,1500,\n"
)


class TestSaisonParser:
    def test_summary_preamble_skipped_and_transactions_parsed(self, tmp_path):
        path = tmp_path / "saison.csv"
        path.write_text(SAMPLE, encoding="cp932")
        txns = parse(path)
        assert len(txns) == 2
        assert all(t.issuer == "saison" for t in txns)
        assert txns[0].description == "サンプルサブスク"
        assert txns[0].amount == 1000

    def test_second_row_parsed_correctly(self, tmp_path):
        path = tmp_path / "saison.csv"
        path.write_text(SAMPLE, encoding="cp932")
        txns = parse(path)
        assert txns[1].description == "サンプルスタンド"
        assert txns[1].amount == 1500


class TestExtractBillingTotal:
    def test_billing_total_extracted_with_leading_zeros(self, tmp_path):
        path = tmp_path / "saison.csv"
        path.write_text(SAMPLE, encoding="cp932")
        assert extract_billing_total(path) == 2500

    def test_missing_summary_returns_none(self, tmp_path):
        path = tmp_path / "saison.csv"
        path.write_text(
            "利用日,ご利用店名及び商品名,利用金額\n2026/07/01,テスト店,100\n", encoding="cp932"
        )
        assert extract_billing_total(path) is None
