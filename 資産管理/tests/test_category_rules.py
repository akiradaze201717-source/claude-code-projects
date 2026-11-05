"""expenses/category_rules.py のユニットテスト。"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from expenses.category_rules import UNCATEGORIZED, classify

RULES = {
    "食費": ["セブン", "ローソン"],
    "通信": ["ドコモ", "docomo"],
    "その他": [],
}


class TestClassify:
    def test_exact_keyword_match(self):
        assert classify("セブン-イレブン渋谷店", RULES) == "食費"

    def test_case_insensitive_match(self):
        assert classify("DOCOMO SHOP", RULES) == "通信"

    def test_first_matching_category_wins(self):
        rules = {"A": ["店"], "B": ["店"]}
        assert classify("何かの店", rules) == "A"

    def test_no_match_returns_uncategorized(self):
        assert classify("謎の店", RULES) == UNCATEGORIZED

    def test_empty_keyword_list_never_matches(self):
        assert classify("その他何か", RULES) != "その他"

    def test_fullwidth_description_matches_halfwidth_keyword(self):
        """カード明細の全角英数字("ＡＢＣ")が半角キーワード("ABC")に一致すること。"""
        rules = {"サブスク": ["ABC"]}
        assert classify("ＡＢＣ．ｃｏｍ", rules) == "サブスク"

    def test_halfwidth_description_matches_fullwidth_keyword(self):
        rules = {"サブスク": ["ＡＢＣ"]}
        assert classify("ABC.com", rules) == "サブスク"
