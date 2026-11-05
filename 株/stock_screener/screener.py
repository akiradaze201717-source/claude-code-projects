"""清原達郎式スクリーニングロジック

清原達郎『わが投資術』の割安小型株スクリーニングを再現する。

ネットキャッシュ（清原式）
    = 流動資産 ＋ 投資有価証券 × 70% − 総負債
ネットキャッシュ比率
    = ネットキャッシュ ÷ 時価総額

投資有価証券を70%評価するのは、含み益にかかる税金等を考慮しているため。
投資有価証券が取得できない銘柄は0として扱う（その種の会社は元々ほぼ
保有しておらず、乖離は小さいことを実測で確認済み）。

清原の代表基準:
    - PER 10倍以下
    - ネットキャッシュ比率 1.0 以上
    - 時価総額 500億円未満（data_fetcher の事前フィルタで担保）
"""

import logging
from dataclasses import dataclass

from 株.stock_screener.data_fetcher import MARKET_CAP_MAX, FinancialData

logger = logging.getLogger(__name__)

INV_SECURITIES_HAIRCUT = 0.70  # 投資有価証券の評価掛け目（清原式）
PER_KIYO_MAX = 10.0  # 清原基準のPER上限
NC_RATIO_PRIMARY = 1.0  # 清原基準のネットキャッシュ比率下限
NC_RATIO_WATCH = 0.70  # 準候補（ウォッチリスト）のネットキャッシュ比率下限
SMALL_CAP_THRESHOLD = 10_000_000_000  # 100億円（小型バッジ用）

# 1単元（100株）の購入額の上限。ユーザー指定で「1単元20万円以下で買える」銘柄に絞る。
# 株価が取得できない銘柄は判定不能として通す（週次の本取得では株価が入る）。
UNIT_SHARES = 100
UNIT_COST_MAX = 200_000  # 円


@dataclass
class ScreeningResult:
    code: str
    name: str
    market: str
    sector: str
    market_cap: float  # 円
    net_cash: float  # ネットキャッシュ（清原式・円）
    net_cash_ratio: float  # ネットキャッシュ / 時価総額
    per: float | None
    cash_ratio: float  # 現金 / 時価総額（参考）
    inv_securities: float  # 投資有価証券（円、取得できなければ0）
    has_inv_data: bool  # 投資有価証券データが取得できたか
    current_price: float | None  # 株価（円）
    unit_cost: float | None  # 1単元購入額 = 株価 × 100（円）
    is_primary: bool  # 清原基準（比率≥1.0 かつ PER≤10）に合致
    is_small_cap: bool


def screen_stocks(financial_data: list[FinancialData]) -> list[ScreeningResult]:
    """スクリーニングを実行し、条件に合致する銘柄を返す。

    通過条件:
      - 本命（is_primary=True）: ネットキャッシュ比率 ≥ 1.0 かつ 0 < PER ≤ 10
      - 準候補（is_primary=False）: ネットキャッシュ比率 ≥ 0.7 かつ 0 < PER ≤ 10

    ネットキャッシュ比率の降順でソート。

    Returns:
        ScreeningResult のリスト
    """
    results = []
    skipped = 0
    processed = 0

    for d in financial_data:
        if d.error:
            skipped += 1
            continue
        if not d.market_cap or d.market_cap <= 0:
            skipped += 1
            continue
        if d.market_cap > MARKET_CAP_MAX:
            skipped += 1
            continue
        if d.current_assets is None or d.total_liabilities is None:
            skipped += 1
            continue

        processed += 1
        # 1単元購入額でフィルタ（株価が判明していて上限超なら除外）
        unit_cost = d.current_price * UNIT_SHARES if d.current_price else None
        if unit_cost is not None and unit_cost > UNIT_COST_MAX:
            continue

        inv = d.investment_securities or 0.0
        # 清原ネットキャッシュ = 流動資産 + 投資有価証券×70% − 総負債
        net_cash = d.current_assets + inv * INV_SECURITIES_HAIRCUT - d.total_liabilities
        net_cash_ratio = net_cash / d.market_cap
        cash = d.cash_and_equivalents or 0
        cash_ratio = cash / d.market_cap

        tier = _classify(net_cash_ratio, d.trailing_pe)
        if tier is None:
            continue

        results.append(
            ScreeningResult(
                code=d.code,
                name=d.name,
                market=d.market,
                sector=d.sector,
                market_cap=d.market_cap,
                net_cash=net_cash,
                net_cash_ratio=net_cash_ratio,
                per=d.trailing_pe,
                cash_ratio=cash_ratio,
                inv_securities=inv,
                has_inv_data=d.investment_securities is not None,
                current_price=d.current_price,
                unit_cost=unit_cost,
                is_primary=(tier == "primary"),
                is_small_cap=d.market_cap < SMALL_CAP_THRESHOLD,
            )
        )

    results.sort(key=lambda r: -r.net_cash_ratio)

    primary_count = sum(1 for r in results if r.is_primary)
    logger.info(
        "スクリーニング完了: 処理%d銘柄 / スキップ%d銘柄 / 該当%d銘柄 "
        "（本命: %d銘柄 / 準候補: %d銘柄）",
        processed,
        skipped,
        len(results),
        primary_count,
        len(results) - primary_count,
    )
    return results


def _classify(net_cash_ratio: float, per: float | None) -> str | None:
    """通過判定。'primary'（清原基準） / 'watch'（準候補） / None（不通過）。"""
    # PERが取得できない、または赤字・PER10超は清原基準から外れる
    if per is None or per <= 0 or per > PER_KIYO_MAX:
        return None
    if net_cash_ratio >= NC_RATIO_PRIMARY:
        return "primary"
    if net_cash_ratio >= NC_RATIO_WATCH:
        return "watch"
    return None


def format_oku(value: float) -> str:
    """円を億円表示にフォーマット。"""
    return f"{value / 100_000_000:.1f}"
