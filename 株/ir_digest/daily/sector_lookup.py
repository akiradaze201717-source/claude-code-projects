"""証券コード→33業種区分のルックアップ（JPX公式銘柄リスト由来）。

JPXの data_j.xls（全上場銘柄・33業種区分を含む）から code→sector を構築。
月次キャッシュ（JSON）を優先し、無ければxlsをDL・解析して生成する。
pandas/xlrd未導入やDL失敗時は空マップを返し、業種は「—」表示で degrade する。
"""

import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

JPX_URL = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ir_digest/1.0"


def get_sector_map(cache_dir: Path, cache_days: int = 30) -> dict[str, str]:
    """4桁コード→33業種区分 の辞書を返す。失敗時は空辞書。"""
    cache_dir.mkdir(parents=True, exist_ok=True)
    json_path = cache_dir / "sector_map.json"

    if _fresh(json_path, cache_days):
        try:
            return json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    try:
        mapping = _build_from_jpx(cache_dir)
    except Exception as e:
        logger.warning("業種マップ生成に失敗（業種は—表示）: %s", e)
        # 古いキャッシュがあれば使う
        if json_path.exists():
            try:
                return json.loads(json_path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    json_path.write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
    logger.info("業種マップ生成: %d 銘柄", len(mapping))
    return mapping


def _fresh(path: Path, max_age_days: int) -> bool:
    if not path.exists():
        return False
    return (time.time() - path.stat().st_mtime) < max_age_days * 86400


def _build_from_jpx(cache_dir: Path) -> dict[str, str]:
    import pandas as pd
    import requests

    xls_path = cache_dir / "jpx_data_j.xls"
    if not _fresh(xls_path, 30):
        resp = requests.get(JPX_URL, headers={"User-Agent": USER_AGENT}, timeout=60)
        resp.raise_for_status()
        xls_path.write_bytes(resp.content)

    df = pd.read_excel(xls_path, dtype={1: str})
    cols = list(df.columns)
    # 固定列: [1]コード [2]銘柄名 [3]市場 [5]33業種区分
    code_col, sector_col = cols[1], cols[5]

    mapping: dict[str, str] = {}
    for _, row in df.iterrows():
        code = str(row[code_col]).strip()
        if len(code) == 5 and code.endswith("0") and code[:4].isdigit():
            code = code[:4]
        sector = str(row.get(sector_col, "")).strip()
        if code.isdigit() and sector and sector != "-":
            mapping[code] = sector
    return mapping
