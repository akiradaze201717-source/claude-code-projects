"""expenses/parsers/jcb_parser.py のユニットテスト。

実データ(MyJCB)で確認した形式: 「今回のお支払日」等のサマリー行 → 「【ご利用明細】」見出し行
→ ヘッダー行(ご利用者,カテゴリ,ご利用日,ご利用先など,ご利用金額(￥),...) → 明細行。
全フィールドがダブルクォートで囲まれている。
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from expenses.parsers.jcb_parser import extract_billing_total, parse

SAMPLE = (
    '"","","今回のお支払日","2026/09/10"\n'
    '"","","今回のお支払金額合計(￥)","3,500"\n'
    '"",""," うち国内ご利用金額合計(￥)","3,500"\n'
    '"",""," うち海外ご利用金額合計(￥)","0"\n'
    '"【ご利用明細】"\n'
    '"ご利用者","カテゴリ","ご利用日","ご利用先など","ご利用金額(￥)","支払区分",'
    '"今回回数","訂正サイン","お支払い金額(￥)","国内／海外","摘要","備考"\n'
    '"****-****-****-0000　【ＯＳ】ＪＣＢカードＷ　ＮＬ　テスト　太郎　様",'
    '"≪ショッピング取組（国内）≫"," 2026/07/17","サンプルストアＡ","500","１回","","",'
    '"500","国内","","* 2"\n'
    '"****-****-****-0000　【ＯＳ】ＪＣＢカードＷ　ＮＬ　テスト　太郎　様",'
    '"≪ショッピング取組（国内）≫"," 2026/07/22","サンプルショップＢ","3,000","１回","","",'
    '"3,000","国内","","* 2"\n'
)


class TestJcbParser:
    def test_summary_preamble_and_section_header_skipped(self, tmp_path):
        path = tmp_path / "jcb.csv"
        path.write_text(SAMPLE, encoding="cp932")
        txns = parse(path)
        assert len(txns) == 2
        assert all(t.issuer == "jcb" for t in txns)

    def test_description_and_amount_parsed(self, tmp_path):
        path = tmp_path / "jcb.csv"
        path.write_text(SAMPLE, encoding="cp932")
        txns = parse(path)
        assert txns[0].description == "サンプルストアＡ"
        assert txns[0].amount == 500

    def test_comma_formatted_amount_parsed(self, tmp_path):
        path = tmp_path / "jcb.csv"
        path.write_text(SAMPLE, encoding="cp932")
        txns = parse(path)
        assert txns[1].amount == 3000

    def test_leading_space_in_date_stripped(self, tmp_path):
        path = tmp_path / "jcb.csv"
        path.write_text(SAMPLE, encoding="cp932")
        txns = parse(path)
        assert txns[0].txn_date.isoformat() == "2026-07-17"


class TestExtractBillingTotal:
    def test_billing_total_extracted(self, tmp_path):
        path = tmp_path / "jcb.csv"
        path.write_text(SAMPLE, encoding="cp932")
        assert extract_billing_total(path) == 3500

    def test_missing_summary_returns_none(self, tmp_path):
        path = tmp_path / "jcb.csv"
        path.write_text(
            '"ご利用日","ご利用先など","ご利用金額(￥)"\n"2026/07/17","テスト店","100"\n',
            encoding="cp932",
        )
        assert extract_billing_total(path) is None
