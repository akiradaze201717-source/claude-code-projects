"""JPX東証銘柄リスト取得・キャッシュモジュール"""

import logging
import time
from dataclasses import dataclass
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: requests が必要です。pip install requests を実行してください")
    raise

try:
    import pandas as pd
except ImportError:
    print("ERROR: pandas が必要です。pip install pandas を実行してください")
    raise

logger = logging.getLogger(__name__)

JPX_STOCK_LIST_URL = (
    "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
)

VALID_MARKETS = {"プライム（内国株式）", "スタンダード（内国株式）", "グロース（内国株式）"}


@dataclass
class StockInfo:
    code: str  # yfinance形式 (例: "1234.T")
    name: str  # 会社名
    market: str  # 市場区分
    sector: str  # 33業種区分


def get_stock_list(cache_dir: str, cache_days: int = 30) -> list[StockInfo]:
    """JPXから東証銘柄リストを取得し、キャッシュする。

    Args:
        cache_dir: キャッシュディレクトリのパス
        cache_days: キャッシュの有効日数

    Returns:
        StockInfoのリスト（プライム/スタンダード/グロースの普通株式のみ）
    """
    cache_path = Path(cache_dir) / "stock_list.xls"
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    if _is_cache_valid(cache_path, cache_days):
        logger.info("キャッシュ済み銘柄リストを使用: %s", cache_path)
    else:
        logger.info("JPXから銘柄リストをダウンロード中...")
        _download_stock_list(cache_path)

    return _parse_stock_list(cache_path)


def _is_cache_valid(path: Path, max_age_days: int) -> bool:
    if not path.exists():
        return False
    age_seconds = time.time() - path.stat().st_mtime
    return age_seconds < max_age_days * 86400


def _download_stock_list(dest: Path) -> None:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    resp = requests.get(JPX_STOCK_LIST_URL, headers=headers, timeout=60)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    logger.info("銘柄リストをダウンロードしました: %s (%d bytes)", dest, len(resp.content))


def _parse_stock_list(path: Path) -> list[StockInfo]:
    df = pd.read_excel(path, dtype={1: str})

    # JPX Excelは固定列構造: 日付, コード, 銘柄名, 市場・商品区分, 33業種コード, 33業種区分, ...
    # 列名がエンコーディングで化ける場合があるため、列位置で取得する
    cols = list(df.columns)
    if len(cols) < 6:
        raise ValueError(
            f"JPX Excelのカラム数が不足しています（{len(cols)}列）。検出カラム: {cols}"
        )

    col_map = {
        "code": cols[1],  # コード
        "name": cols[2],  # 銘柄名
        "market": cols[3],  # 市場・商品区分
        "sector": cols[5],  # 33業種区分
    }

    stocks = []
    for _, row in df.iterrows():
        market = str(row.get(col_map["market"], "")).strip()
        if market not in VALID_MARKETS:
            continue

        code_raw = str(row[col_map["code"]]).strip()
        if not code_raw.isdigit():
            continue

        stocks.append(
            StockInfo(
                code=f"{code_raw}.T",
                name=str(row[col_map["name"]]).strip(),
                market=market.replace("（内国株式）", ""),
                sector=str(row.get(col_map.get("sector", ""), "")).strip(),
            )
        )

    logger.info("銘柄リスト解析完了: %d銘柄（プライム/スタンダード/グロース）", len(stocks))
    return stocks
