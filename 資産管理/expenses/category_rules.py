"""摘要文字列 → 支出カテゴリ のキーワードマッチング分類。

category_rules.json のキーワード辞書はユーザーが育てていく運用。
マッチしない取引は「未分類」に落とし、ダッシュボードで強調表示する。

注意:
- 単純な部分一致（大文字小文字を無視した substring match）のため、
  "au" のような短い英字キーワードは無関係な単語（例: "Claude" の中の "au"）に
  誤って一致することがある。キーワードを追加する際は、できるだけ具体的な
  文字列（例: "au一括請求" "auでんき"）を使うこと。
- カード会社のCSVは "ＡＢＣ" のように英数字が全角で出てくることが多い。
  半角キーワード("ABC")では一致しないため、NFKC正規化（全角→半角統一）してから
  比較している。キーワード自体はどちらの表記で登録しても一致する。
"""

import json
import unicodedata
from pathlib import Path

RULES_PATH = Path(__file__).parent / "category_rules.json"
UNCATEGORIZED = "未分類"


def load_rules(path: Path = RULES_PATH) -> dict[str, list[str]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize(text: str) -> str:
    """全角英数字・記号を半角に統一し、小文字化する（NFKC正規化）。"""
    return unicodedata.normalize("NFKC", text).lower()


def classify(description: str, rules: dict[str, list[str]]) -> str:
    """摘要にキーワードが含まれる最初のカテゴリを返す。どれにも一致しなければ「未分類」。"""
    normalized_desc = _normalize(description)
    for category, keywords in rules.items():
        for keyword in keywords:
            if _normalize(keyword) in normalized_desc:
                return category
    return UNCATEGORIZED
