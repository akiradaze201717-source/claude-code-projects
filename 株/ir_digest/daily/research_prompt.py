r"""④（自社株買い・資本政策）企業の「調査プロンプト」自動生成。

毎日の④開示から、既存 `個別銘柄調査\調査プロンプト.html` のブリーフを踏襲した
「貼り付けるだけ」のプロンプトを生成する。実際のフル調査はユーザーがこの
プロンプトをClaudeに貼って実行する（ツール自体はLLMを呼ばない＝費用ゼロ）。
"""

import glob
import logging
from pathlib import Path

from tdnet_fetcher import Disclosure, buyback_subtype, is_new_capital_return

logger = logging.getLogger(__name__)

# 調査プロンプト.html「クイック起動プロンプト」準拠のブリーフ本文
BRIEF = """\
以下の証券コードの会社を調査して、株\\個別銘柄調査\\ に <CODE>_<社名>.html として保存して。
index.html の一覧と比較表にも追記して。
※ 既に {code}_*.html が存在する銘柄はスキップしてよい。

前提スタンス: 基本は長期保有。自社株買いをする還元株を中心に見ている。
重視する順: ① 競争優位性（モート） ② これからの展望 ③ 株主還元（自社株買い・配当）

既存の 3443 / 4095 と同じHTMLフォーマット・デザインで、Chart.js で
業績推移・ROE/自己資本比率・EPS/配当・自社株買い履歴の図を入れて。
数字は IRBANK・株探・会社IR・四季報から取り、調査時点の参考値である旨を明記。
曖昧な点・確認しきれなかった数値は「論点・確認すべきこと」に ToDo として残して。
曖昧なところは先に質問して。

出力章立て（各ページ）:
① ひとことサマリー ② 主要指標カード(PER/PBR/EPS/BPS/ROE/自己資本比率/配当利回り/時価総額)
③ 業績の推移(図) ④ 競争優位性(モート) ⑤ これからの展望(中計・強気/弱気)
⑥ 株主還元(配当・自社株買い・還元余力)【重視】 ⑦ 論点・確認すべきこと ⑧ 参考リンク

件数が多い場合は、上から（新規買い→消却→自社TOB）優先で必要な数だけ調査すればよい。"""


def _existing_codes(research_dir: Path) -> set[str]:
    """個別銘柄調査フォルダに既にHTMLがある証券コードの集合。"""
    codes = set()
    if not research_dir.exists():
        return codes
    for p in glob.glob(str(research_dir / "*_*.html")):
        name = Path(p).name
        head = name.split("_", 1)[0]
        if head:
            codes.add(head)
    return codes


def build(
    disclosures: list[Disclosure], research_dir: Path, date_disp: str, exclude_sectors=()
) -> tuple[str, int]:
    """④企業を埋め込んだ調査プロンプト文字列を生成。

    Returns: (プロンプト文字列, 対象会社数)
    exclude_sectors: 除外する33業種区分のリスト（例: ["情報・通信業"]）。
    """
    existing = _existing_codes(research_dir)
    exclude_sectors = set(exclude_sectors or ())

    # ④のうち「新規の還元イベント」（新規自社株買い・消却・自社TOB）を会社コードで
    # 集約（同社の複数開示は1行に）。既存ファイル・除外業種は除く。
    by_code: dict[str, Disclosure] = {}
    for d in disclosures:
        if not is_new_capital_return(d.title):
            continue
        if d.code in existing:
            continue
        if d.sector and d.sector in exclude_sectors:
            continue
        # サブ種別の優先度が高い（数値が小さい）開示を代表に採用
        prev = by_code.get(d.code)
        if prev is None or buyback_subtype(d.title)[1] < buyback_subtype(prev.title)[1]:
            by_code[d.code] = d

    companies = sorted(
        by_code.values(),
        key=lambda d: (buyback_subtype(d.title)[1], d.code),
    )

    if not companies:
        body = "（本日は新規の自社株買い・消却・自社TOB の未調査対象はありませんでした）"
        codes_line = ""
    else:
        lines = []
        for d in companies:
            label = buyback_subtype(d.title)[0]
            sector = d.sector or "—"
            lines.append(f"- {d.code} {d.company}（{sector}）｜{label}｜{d.title}")
        body = "\n".join(lines)
        codes_line = "証券コード: " + ", ".join(d.code for d in companies)

    prompt = f"""# ④自社株買い・資本政策 調査プロンプト（{date_disp}）

{BRIEF}

{codes_line}

## 当日の④新規イベント（自社株買い・消却・自社TOB）{len(companies)}社・既調査は除外済み・優先度順
{body}
"""
    return prompt, len(companies)


def write(
    disclosures: list[Disclosure],
    research_dir: Path,
    date_yyyymmdd: str,
    date_disp: str,
    exclude_sectors=(),
) -> tuple[Path | None, int, str]:
    """プロンプトを RESEARCH_DIR に保存。Returns: (保存パス, 会社数, プロンプト文字列)。"""
    prompt, n = build(disclosures, research_dir, date_disp, exclude_sectors)
    try:
        research_dir.mkdir(parents=True, exist_ok=True)
        dated = research_dir / f"_daily_prompt_{date_yyyymmdd}.md"
        dated.write_text(prompt, encoding="utf-8")
        (research_dir / "_daily_prompt_latest.md").write_text(prompt, encoding="utf-8")
        return dated, n, prompt
    except Exception as e:
        logger.warning("調査プロンプトの保存に失敗: %s", e)
        return None, n, prompt
