"""RSI(14) Wilder's Smoothed 計算モジュール"""

from datetime import datetime

from gmo_api import GmoApi, GmoApiError


def fetch_closing_prices(api: GmoApi, symbol: str) -> list[float]:
    """GMO K-line API から日足終値を取得。

    最低28日分が必要（RSI14 のウォームアップ）。
    日足klines APIは年単位指定のため、今年と去年の2年分を取得して結合する。
    """
    today = datetime.now()
    # 日足APIは YYYY 形式で年を指定する
    dates = {today.strftime("%Y"), str(today.year - 1)}

    candles: dict[str, float] = {}  # date_key -> close
    for date_str in sorted(dates):
        try:
            klines = api.get_klines(symbol, date_str)
        except GmoApiError:
            continue
        for k in klines:
            # openTime はミリ秒 UNIX timestamp
            ts = int(k.get("openTime", 0)) // 1000
            day_key = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            candles[day_key] = float(k.get("close", 0))

    # 日付順にソートして終値リストを返す
    sorted_prices = [candles[k] for k in sorted(candles.keys())]
    return sorted_prices


def compute_rsi(closing_prices: list[float], period: int = 14) -> float:
    """Wilder's Smoothed RSI を計算。

    closing_prices: 日付昇順の終値リスト（最低 period+1 個必要、推奨 2*period 個以上）
    Returns: RSI値（0-100）
    Raises: ValueError データ不足時
    """
    if len(closing_prices) < period + 1:
        raise ValueError(
            f"RSI計算に最低{period + 1}個の終値が必要ですが、{len(closing_prices)}個しかありません"
        )

    # 価格変動
    changes = [closing_prices[i] - closing_prices[i - 1] for i in range(1, len(closing_prices))]
    gains = [max(0.0, c) for c in changes]
    losses = [max(0.0, -c) for c in changes]

    # 最初の period 日間の SMA でシード値を計算
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    # Wilder's Smoothing で残りを処理
    for i in range(period, len(changes)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def get_rsi(api: GmoApi, symbol: str) -> float:
    """銘柄のRSI(14)を算出して返す。

    symbol: "BTC" や "ETH"（K-line用の短縮名）
    Raises: ValueError or GmoApiError
    """
    prices = fetch_closing_prices(api, symbol)
    return compute_rsi(prices)
