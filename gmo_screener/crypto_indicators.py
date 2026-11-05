"""暗号資産テクニカル指標計算モジュール（純Python実装）"""

import math
from datetime import datetime

from gmo_api import GmoApi, GmoApiError


# ------------------------------------------------------------------ 価格取得
def fetch_closing_prices(api: GmoApi, symbol: str, num_months: int = 3) -> list[float]:
    """GMO K-line APIから日足終値を取得。

    日足klines APIは年単位指定のため、今年と去年の2年分を取得して結合する。
    MACD(12,26,9) の計算に最低34本必要。
    """
    today = datetime.now()
    # 日足APIは YYYY 形式で年を指定する（num_months は互換性のため残すが内部では年単位）
    dates: set[str] = {today.strftime("%Y"), str(today.year - 1)}

    candles: dict[str, float] = {}
    for date_str in dates:
        try:
            klines = api.get_klines(symbol, date_str)
        except GmoApiError:
            continue
        for k in klines:
            ts = int(k.get("openTime", 0)) // 1000
            day_key = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            candles[day_key] = float(k.get("close", 0))

    return [candles[k] for k in sorted(candles.keys())]


# ------------------------------------------------------------------ 内部ヘルパー
def _ema(prices: list[float], period: int) -> list[float]:
    """指数移動平均（EMA）。出力長 = len(prices) - period + 1。"""
    if len(prices) < period:
        return []
    k = 2.0 / (period + 1)
    result = [sum(prices[:period]) / period]
    for p in prices[period:]:
        result.append(p * k + result[-1] * (1 - k))
    return result


def _sma(prices: list[float], period: int) -> list[float]:
    """単純移動平均（SMA）。出力長 = len(prices) - period + 1。"""
    if len(prices) < period:
        return []
    return [sum(prices[i : i + period]) / period for i in range(len(prices) - period + 1)]


# ------------------------------------------------------------------ 公開指標
def compute_ma_crossover(prices: list[float], short: int = 5, long: int = 20) -> dict:
    """移動平均クロスオーバーを計算。

    Returns:
        short_ma, long_ma, cross_type ("golden"/"dead"/"none"), days_since_cross
    """
    sma_short = _sma(prices, short)
    sma_long = _sma(prices, long)
    if not sma_short or not sma_long:
        return {"short_ma": 0.0, "long_ma": 0.0, "cross_type": "none", "days_since_cross": -1}

    # sma_long の長さに合わせて sma_short を末尾揃えでトリム
    offset = len(sma_short) - len(sma_long)
    aligned = sma_short[offset:]

    cross_type = "none"
    days_since_cross = -1
    n = len(sma_long)
    for i in range(n - 1, 0, -1):
        curr = aligned[i] - sma_long[i]
        prev = aligned[i - 1] - sma_long[i - 1]
        if curr > 0 and prev <= 0:
            cross_type = "golden"
            days_since_cross = n - 1 - i
            break
        if curr < 0 and prev >= 0:
            cross_type = "dead"
            days_since_cross = n - 1 - i
            break

    return {
        "short_ma": aligned[-1],
        "long_ma": sma_long[-1],
        "cross_type": cross_type,
        "days_since_cross": days_since_cross,
    }


def compute_macd(prices: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """MACD・シグナル・ヒストグラムを計算。

    Returns:
        macd_line, signal_line, histogram, histogram_increasing
    """
    ema_fast = _ema(prices, fast)
    ema_slow = _ema(prices, slow)
    if not ema_fast or not ema_slow:
        return {
            "macd_line": 0.0,
            "signal_line": 0.0,
            "histogram": 0.0,
            "histogram_increasing": False,
        }

    # ema_slow の長さに合わせてトリム
    offset = len(ema_fast) - len(ema_slow)
    macd_line = [f - s for f, s in zip(ema_fast[offset:], ema_slow)]

    sig_ema = _ema(macd_line, signal)
    if not sig_ema:
        return {
            "macd_line": macd_line[-1],
            "signal_line": 0.0,
            "histogram": 0.0,
            "histogram_increasing": False,
        }

    # sig_ema の長さに合わせてトリム
    m_offset = len(macd_line) - len(sig_ema)
    macd_aligned = macd_line[m_offset:]
    histogram = [m - s for m, s in zip(macd_aligned, sig_ema)]

    current_hist = histogram[-1]
    prev_hist = histogram[-2] if len(histogram) >= 2 else current_hist

    return {
        "macd_line": macd_aligned[-1],
        "signal_line": sig_ema[-1],
        "histogram": current_hist,
        "histogram_increasing": current_hist > prev_hist,
    }


def compute_bollinger(prices: list[float], period: int = 20, num_std: float = 2.0) -> dict:
    """ボリンジャーバンドを計算。

    Returns:
        upper, middle, lower, pct_b (0=下限 / 1=上限), bandwidth
    """
    if len(prices) < period:
        return {"upper": 0.0, "middle": 0.0, "lower": 0.0, "pct_b": 0.5, "bandwidth": 0.0}

    window = prices[-period:]
    middle = sum(window) / period
    variance = sum((p - middle) ** 2 for p in window) / period
    std = math.sqrt(variance)
    upper = middle + num_std * std
    lower = middle - num_std * std
    band_width = upper - lower
    pct_b = (prices[-1] - lower) / band_width if band_width > 0 else 0.5

    return {
        "upper": upper,
        "middle": middle,
        "lower": lower,
        "pct_b": pct_b,
        "bandwidth": band_width / middle if middle > 0 else 0.0,
    }
