"""TDnet適時開示一覧の取得モジュール。

データ源は多層構成（単一障害点を作らない）:
  1) TDnet公式サイト直接取得（https://www.release.tdnet.info/） … 第一候補
  2) yanoshin TDnet WebAPI（JSON）            … 公式が失敗した時のフォールバック

公式取得はPDF/XBRL(zip)リンクまで取得できるが、yanoshinは一覧+PDFのみ
（XBRLリンクは持たない）。乖離分析にはXBRLが要るため公式を優先する。
"""

import logging
import time
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

TDNET_BASE = "https://www.release.tdnet.info/inbs/"
TDNET_LIST_URL = TDNET_BASE + "I_list_{page:03d}_{date}.html"
YANOSHIN_URL = "https://webapi.yanoshin.jp/webapi/tdnet/list/{cond}.json"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ir_digest/1.0 (personal IR research tool)"
REQUEST_TIMEOUT = 20
POLITE_DELAY = 0.4  # 公式サイトへの連続アクセス間隔（礼儀）
MAX_PAGES = 30  # 1日あたり最大ページ数（100件/頁 → 3000件で打ち切り）

# --- 開示種別の分類キーワード（タイトルから判定） ---
CAT_EARNINGS = "決算短信"
CAT_FORECAST = "業績予想修正"
CAT_DIVIDEND = "配当予想修正"
CAT_BUYBACK = "自社株買い・資本政策"  # 自己株式取得/消却・株式分割・優待・TOB 等
CAT_OTHER = "その他適時開示"

# 自己株式の「処分」系（報酬・持株会・第三者割当）は株主還元でないため除外する語
_COMP_DISPOSAL = (
    "処分",
    "譲渡制限付",
    "報酬",
    "持株会",
    "ストック",
    "インセンティブ",
    "第三者割当",
    "ＲＳ",
    "ＥＳＯＰ",
    "ESOP",
)


@dataclass
class Disclosure:
    """1件の適時開示。"""

    time: str  # 開示時刻 "HH:MM"
    code: str  # 証券コード（4桁に正規化）
    company: str  # 会社名
    title: str  # 開示タイトル
    category: str  # 上記 CAT_* のいずれか
    pdf_url: str | None = None
    xbrl_url: str | None = None  # サマリーXBRL zip（公式取得時のみ）
    market: str = ""
    sector: str = ""  # 33業種区分（JPXリストから補完）
    source: str = ""  # "tdnet" | "yanoshin"


def fetch_disclosures(date_yyyymmdd: str) -> tuple[list[Disclosure], str]:
    """指定日の全開示を取得する。

    Returns: (開示リスト, 使用したデータ源名)
    公式 → yanoshin の順に試し、最初に成功した結果を返す。
    両方失敗した場合は例外を送出する。
    """
    # 1) TDnet公式
    try:
        items = _fetch_from_tdnet_official(date_yyyymmdd)
        if items:
            logger.info("TDnet公式から %d 件取得", len(items))
            return items, "tdnet"
        logger.warning("TDnet公式: 0件。yanoshinにフォールバックします")
    except Exception as e:
        logger.warning("TDnet公式の取得に失敗（%s）。yanoshinにフォールバック", e)

    # 2) yanoshin フォールバック
    items = _fetch_from_yanoshin(date_yyyymmdd)
    logger.info("yanoshin から %d 件取得（※XBRLリンクなし）", len(items))
    return items, "yanoshin"


# ---------------------------------------------------------------------------
# TDnet公式
# ---------------------------------------------------------------------------
def _fetch_from_tdnet_official(date_yyyymmdd: str) -> list[Disclosure]:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    all_items: list[Disclosure] = []
    total_pages = None

    for page in range(1, MAX_PAGES + 1):
        url = TDNET_LIST_URL.format(page=page, date=date_yyyymmdd)
        resp = session.get(url, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            break
        if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
            resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        page_items = _parse_official_page(soup)
        if not page_items:
            break
        all_items.extend(page_items)

        if total_pages is None:
            total_pages = _parse_total_pages(soup)
        if total_pages is not None and page >= total_pages:
            break
        time.sleep(POLITE_DELAY)

    return all_items


def _parse_official_page(soup: BeautifulSoup) -> list[Disclosure]:
    """公式一覧ページのテーブル行を Disclosure に変換。"""
    table = soup.find("table", id="main-list-table")
    if table is None:
        return []

    items: list[Disclosure] = []
    for tr in table.find_all("tr"):
        t = _cell_text(tr, "kjTime")
        code_raw = _cell_text(tr, "kjCode")
        name = _cell_text(tr, "kjName")
        title_cell = tr.find("td", class_="kjTitle")
        if not code_raw or title_cell is None:
            continue

        title_a = title_cell.find("a")
        title = title_a.get_text(strip=True) if title_a else title_cell.get_text(strip=True)
        pdf_url = _abs_url(title_a.get("href")) if title_a else None

        xbrl_cell = tr.find("td", class_="kjXbrl")
        xbrl_url = None
        if xbrl_cell is not None:
            xbrl_a = xbrl_cell.find("a")
            if xbrl_a and xbrl_a.get("href"):
                xbrl_url = _abs_url(xbrl_a.get("href"))

        market = _cell_text(tr, "kjPlace")

        items.append(
            Disclosure(
                time=t,
                code=_normalize_code(code_raw),
                company=name,
                title=title,
                category=classify(title),
                pdf_url=pdf_url,
                xbrl_url=xbrl_url,
                market=market,
                source="tdnet",
            )
        )
    return items


def _parse_total_pages(soup: BeautifulSoup) -> int | None:
    """ページャから総ページ数を推定（取れなければNone）。"""
    pager = soup.find("div", class_="pager-M")
    if pager is None:
        return None
    # ページャ内の I_list_xxx リンク番号の最大値を総ページ数とみなす
    max_page = 0
    for a in pager.find_all("a"):
        href = a.get("href", "")
        # I_list_003_20260602.html → 003
        for token in href.replace(".html", "").split("_"):
            if token.isdigit() and len(token) == 3:
                max_page = max(max_page, int(token))
    return max_page or None


def _cell_text(tr, class_name: str) -> str:
    td = tr.find("td", class_=class_name)
    return td.get_text(strip=True) if td else ""


def _abs_url(href: str | None) -> str | None:
    if not href:
        return None
    if href.startswith("http"):
        return href
    return TDNET_BASE + href.lstrip("/")


# ---------------------------------------------------------------------------
# yanoshin フォールバック
# ---------------------------------------------------------------------------
def _fetch_from_yanoshin(date_yyyymmdd: str) -> list[Disclosure]:
    cond = date_yyyymmdd
    url = YANOSHIN_URL.format(cond=cond)
    resp = requests.get(
        url,
        params={"limit": 2000},
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()

    items: list[Disclosure] = []
    for entry in data.get("items", []):
        rec = entry.get("Tdnet", entry)
        pubdate = rec.get("pubdate", "")  # "2026-06-02 15:00:00"
        t = pubdate.split(" ")[1][:5] if " " in pubdate else ""
        title = rec.get("title", "")
        items.append(
            Disclosure(
                time=t,
                code=_normalize_code(str(rec.get("company_code", ""))),
                company=rec.get("company_name", ""),
                title=title,
                category=classify(title),
                pdf_url=rec.get("document_url") or rec.get("url"),
                xbrl_url=None,  # yanoshinはXBRL zipを持たない
                market=rec.get("markets_string", ""),
                source="yanoshin",
            )
        )
    return items


# ---------------------------------------------------------------------------
# 共通ユーティリティ
# ---------------------------------------------------------------------------
def classify(title: str) -> str:
    """開示タイトルから種別を分類する。"""
    if CAT_EARNINGS in title or "決算短信" in title:
        return CAT_EARNINGS
    if "業績予想" in title and "修正" in title:
        return CAT_FORECAST
    if "配当予想" in title and "修正" in title:
        return CAT_DIVIDEND
    if _is_buyback_or_capital(title):
        return CAT_BUYBACK
    return CAT_OTHER


def _is_buyback_or_capital(title: str) -> bool:
    """自社株買い・資本政策・株主還元系か（報酬目的の自己株処分は除外）。"""
    # 報酬・希薄化目的の自己株式の処分は対象外
    if "自己株式" in title and any(w in title for w in _COMP_DISPOSAL):
        return False
    if "自己株式" in title and (
        "取得" in title
        or "買付" in title
        or "立会外" in title
        or "ToSTNeT" in title
        or "ＴｏＳＴＮｅＴ" in title
    ):
        return True
    if "自己株式" in title and "消却" in title:
        return True
    if "自社株買い" in title:
        return True
    if "株式分割" in title:
        return True
    if "株主優待" in title:
        return True
    if "公開買付" in title or "ＴＯＢ" in title or "TOB" in title:
        return True
    return False


def is_forthcoming_buyback(title: str) -> bool:
    """「これから自社株買いを行う」新規発表か。

    対象: 自己株式の取得枠設定 / 取得に係る事項の決定 / 立会外買付(ToSTNeT-3) など
    除外: 取得状況・途中経過・取得終了・結果（=過去/進捗）、消却、報酬目的の処分、
          調査報告書など。
    """
    if not _is_buyback_or_capital(title):
        return False
    # 取得・買付の意思表示があること
    if not any(
        w in title for w in ("取得", "買付", "自社株買い", "立会外", "ToSTNeT", "ＴｏＳＴＮｅＴ")
    ):
        return False
    # 過去/進捗/別件を除外
    exclude = (
        "状況",
        "途中経過",
        "終了",
        "完了",
        "結果",
        "報告書",
        "調査",
        "委員会",
        "訂正",
        "消却",
        "株式分割",
        "株主優待",
        "公開買付",
        "ＴＯＢ",
        "TOB",
    )
    if any(w in title for w in exclude):
        return False
    return True


def is_new_capital_return(title: str) -> bool:
    """④のうち「新規の還元イベント」か。

    含める: 新規の自社株買い（取得枠/事項決定/ToSTNeT・市場買付の開始）
            / 自己株式の消却（発表） / 自社による公開買付(TOB)
    除外:   取得状況・途中経過・取得結果・終了・完了（=過去/進捗）、
            株式分割・株主優待（今回の対象外）、報酬目的の自己株処分。
    """
    if not _is_buyback_or_capital(title):
        return False
    # 過去・進捗・別件を除外
    past = ("状況", "途中経過", "終了", "完了", "結果", "報告書", "調査", "委員会", "訂正")
    if any(w in title for w in past):
        return False
    # 含める種別
    if is_forthcoming_buyback(title):  # 新規の自社株買い
        return True
    if "消却" in title:  # 自己株式の消却（発表）
        return True
    # 自社によるTOB＝自己株式の公開買付け（セルフ）に限定。
    # 第三者による買収TOB（「○○による当社株式に対する公開買付」等）は除外。
    if ("公開買付" in title or "ＴＯＢ" in title or "TOB" in title) and "自己株式" in title:
        return True
    return False


# 資本政策系のサブ種別ラベルと表示優先度（小さいほど上位）
def buyback_subtype(title: str) -> tuple[str, int]:
    if "公開買付" in title or "TOB" in title or "ＴＯＢ" in title:
        return ("公開買付(TOB)", 5)
    if "消却" in title:
        return ("自己株式消却", 2)
    if "株式分割" in title:
        return ("株式分割", 3)
    if "株主優待" in title:
        return ("株主優待", 4)
    if "取得状況" in title or "途中経過" in title:
        return ("自己株取得・進捗", 6)
    if "立会外" in title or "ToSTNeT" in title or "ＴｏＳＴＮｅＴ" in title or "買付" in title:
        return ("自己株取得・買付", 1)
    if "取得" in title:
        return ("自己株取得・新規枠", 0)
    return ("資本政策", 7)


def _normalize_code(code_raw: str) -> str:
    """5桁コード（4桁+チェック桁0）を4桁に正規化。英字混在コードはそのまま。"""
    code = code_raw.strip()
    if len(code) == 5 and code.endswith("0") and code[:4].isdigit():
        return code[:4]
    return code


def is_analyzable(d: Disclosure) -> bool:
    """乖離分析の対象（決算短信・業績予想修正）かどうか。"""
    return d.category in (CAT_EARNINGS, CAT_FORECAST)
