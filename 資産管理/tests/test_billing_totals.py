"""expenses/billing_totals.py のユニットテスト。"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from expenses.billing_totals import fetch_card_billing_totals


def _write(tmp_path, issuer, filename, content):
    d = tmp_path / issuer
    d.mkdir(parents=True, exist_ok=True)
    (d / filename).write_text(content, encoding="cp932")


class TestFetchCardBillingTotals:
    def test_extracts_from_all_three_issuers(self, tmp_path):
        _write(
            tmp_path,
            "smbc",
            "a.csv",
            "名義,カード番号,カード名,,,,\n2026/7/1,店,100,1,1,100,\n,,,,,100,\n",
        )
        _write(
            tmp_path,
            "saison",
            "b.csv",
            "カード名称,セゾン\nお支払日,2026/09/04\n今回ご請求額,0000008524\n\n"
            "利用日,ご利用店名及び商品名,利用金額\n2026/07/01,店,990\n",
        )
        _write(
            tmp_path,
            "jcb",
            "c.csv",
            '"","","今回のお支払日","2026/09/10"\n"","","今回のお支払金額合計(￥)","10,975"\n'
            '"【ご利用明細】"\n"ご利用者","カテゴリ","ご利用日","ご利用先など","ご利用金額(￥)"\n'
            '"x","y"," 2026/07/17","店","550"\n',
        )

        totals = fetch_card_billing_totals(incoming_dir=tmp_path)
        assert totals == {"smbc_card": 100.0, "saison_gold": 8524.0, "jcb_card": 10975.0}

    def test_missing_issuer_dir_excluded(self, tmp_path):
        _write(
            tmp_path,
            "smbc",
            "a.csv",
            "名義,カード番号,カード名,,,,\n2026/7/1,店,100,1,1,100,\n,,,,,100,\n",
        )
        totals = fetch_card_billing_totals(incoming_dir=tmp_path)
        assert totals == {"smbc_card": 100.0}

    def test_no_files_returns_empty_dict(self, tmp_path):
        assert fetch_card_billing_totals(incoming_dir=tmp_path) == {}

    def test_unextractable_file_excluded(self, tmp_path):
        _write(
            tmp_path, "smbc", "a.csv", "名義,カード番号,カード名,,,,\n2026/7/1,店,100,1,1,100,\n"
        )
        totals = fetch_card_billing_totals(incoming_dir=tmp_path)
        assert "smbc_card" not in totals
