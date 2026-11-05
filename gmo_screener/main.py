"""
BTC テクニカルシグナル通知ボット
RSI(14)・MA(5/20)・MACD(12/26/9)・BB(20) の4指標で BUY/SELL/HOLD を判定し、
BUY または SELL のときのみメール通知する。
"""

import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from gmo_api import GmoApi, GmoApiError

load_dotenv(Path(__file__).parent / "config.env")
from crypto_indicators import (
    compute_bollinger,
    compute_ma_crossover,
    compute_macd,
    fetch_closing_prices,
)
from log_setup import setup_logger
from notifier import notify_screener_signal
from rsi import compute_rsi

# ------------------------------------------------------------------ 定数
JST = timezone(timedelta(hours=9))

SYMBOL = "BTC"

BUY_THRESHOLD = 30.0
SELL_THRESHOLD = -30.0

setup_logger("screener.log")
log = logging.getLogger(__name__)

# 最低データ数: MACD(12,26,9) は 26+9-1=34 本必要
MIN_PRICES = 34


# ------------------------------------------------------------------ スコアリング
def _score_rsi(rsi: float) -> tuple[float, str]:
    if rsi < 30:
        return 100, f"RSI {rsi:.1f} < 30（売られすぎ → 強い買い）"
    elif rsi < 40:
        return 50, f"RSI {rsi:.1f} < 40（やや売られすぎ）"
    elif rsi < 50:
        return 20, f"RSI {rsi:.1f}（やや売られ気味）"
    elif rsi <= 60:
        return -20, f"RSI {rsi:.1f}（やや買われ気味）"
    elif rsi <= 70:
        return -50, f"RSI {rsi:.1f} ≤ 70（やや買われすぎ）"
    else:
        return -100, f"RSI {rsi:.1f} > 70（買われすぎ → 強い売り）"


def _score_ma(
    cross_type: str, days_since_cross: int, short_ma: float, long_ma: float
) -> tuple[float, str]:
    if cross_type == "golden" and days_since_cross <= 5:
        return 100, f"ゴールデンクロス（{days_since_cross}日前）→ 強い買い"
    elif cross_type == "dead" and days_since_cross <= 5:
        return -100, f"デッドクロス（{days_since_cross}日前）→ 強い売り"
    elif short_ma > long_ma:
        return 40, f"短期MA({short_ma:,.0f}) > 長期MA({long_ma:,.0f}) → 上昇トレンド"
    elif short_ma < long_ma:
        return -40, f"短期MA({short_ma:,.0f}) < 長期MA({long_ma:,.0f}) → 下降トレンド"
    return 0, "短期MAと長期MAが同水準"


def _score_macd(
    macd_line: float, signal_line: float, histogram: float, hist_increasing: bool
) -> tuple[float, str]:
    if macd_line > signal_line and hist_increasing:
        return 100, f"MACD > シグナル + ヒストグラム増加（{histogram:+,.0f}）→ 強い買い"
    elif macd_line > signal_line:
        return 50, f"MACD({macd_line:+,.0f}) > シグナル({signal_line:+,.0f}) → 買い優勢"
    elif macd_line < signal_line and not hist_increasing:
        return -100, f"MACD < シグナル + ヒストグラム減少（{histogram:+,.0f}）→ 強い売り"
    elif macd_line < signal_line:
        return -50, f"MACD({macd_line:+,.0f}) < シグナル({signal_line:+,.0f}) → 売り優勢"
    return 0, "MACDとシグナルが同水準"


def _score_bollinger(
    pct_b: float, current_price: float, upper: float, lower: float
) -> tuple[float, str]:
    if pct_b < 0.0:
        return 100, f"価格({current_price:,.0f})がBB下限({lower:,.0f})を下回り → 強い買い"
    elif pct_b < 0.2:
        return 60, f"%B={pct_b:.2f} バンド下部 → 買いシグナル"
    elif pct_b < 0.4:
        return 20, f"%B={pct_b:.2f} やや下寄り"
    elif pct_b <= 0.6:
        return 0, f"%B={pct_b:.2f} バンド中央付近"
    elif pct_b <= 0.8:
        return -20, f"%B={pct_b:.2f} やや上寄り"
    elif pct_b <= 1.0:
        return -60, f"%B={pct_b:.2f} バンド上部 → 売りシグナル"
    else:
        return -100, f"価格({current_price:,.0f})がBB上限({upper:,.0f})を上回り → 強い売り"


def _compute_confidence(indicator_scores: dict, direction: str) -> str:
    scores = list(indicator_scores.values())
    if direction == "buy":
        agreeing = sum(1 for s in scores if s > 0)
    elif direction == "sell":
        agreeing = sum(1 for s in scores if s < 0)
    else:
        return "LOW"
    if agreeing >= 3:
        return "HIGH"
    elif agreeing >= 2:
        return "MEDIUM"
    return "LOW"


# ------------------------------------------------------------------ シグナル生成
def generate_signal(api: GmoApi) -> dict:
    """BTCのテクニカルシグナルを生成して辞書で返す。"""
    log.info("BTC: 価格データ取得中...")
    prices = fetch_closing_prices(api, SYMBOL)
    if len(prices) < MIN_PRICES:
        raise ValueError(f"データ不足: {len(prices)}本（最低{MIN_PRICES}本必要）")
    log.info(f"BTC: {len(prices)}本の終値を取得")

    ticker = api.get_ticker(SYMBOL)
    current_price = float(ticker.get("last", prices[-1]))
    date_str = datetime.now(JST).strftime("%Y-%m-%d")

    # 各指標計算
    rsi = compute_rsi(prices)
    log.info(f"BTC: RSI(14) = {rsi:.1f}")

    ma = compute_ma_crossover(prices)
    log.info(
        f"BTC: MA 短期={ma['short_ma']:,.0f} / 長期={ma['long_ma']:,.0f} / クロス={ma['cross_type']}"
    )

    macd = compute_macd(prices)
    log.info(f"BTC: MACD={macd['macd_line']:+,.0f} / シグナル={macd['signal_line']:+,.0f}")

    bb = compute_bollinger(prices)
    log.info(f"BTC: BB 上限={bb['upper']:,.0f} / 下限={bb['lower']:,.0f} / %B={bb['pct_b']:.2f}")

    # スコア計算
    rsi_score, rsi_reason = _score_rsi(rsi)
    ma_score, ma_reason = _score_ma(
        ma["cross_type"], ma["days_since_cross"], ma["short_ma"], ma["long_ma"]
    )
    macd_score, macd_reason = _score_macd(
        macd["macd_line"],
        macd["signal_line"],
        macd["histogram"],
        macd["histogram_increasing"],
    )
    bb_score, bb_reason = _score_bollinger(bb["pct_b"], current_price, bb["upper"], bb["lower"])

    indicator_scores = {"RSI": rsi_score, "MA": ma_score, "MACD": macd_score, "BB": bb_score}
    tech_score = sum(indicator_scores.values()) / 4.0
    reasons = [rsi_reason, ma_reason, macd_reason, bb_reason]

    log.info(f"BTC: テクニカルスコア = {tech_score:+.1f}")

    # シグナル判定
    if tech_score >= BUY_THRESHOLD:
        signal = "BUY"
        confidence = _compute_confidence(indicator_scores, "buy")
    elif tech_score <= SELL_THRESHOLD:
        signal = "SELL"
        confidence = _compute_confidence(indicator_scores, "sell")
    else:
        signal = "HOLD"
        confidence = "LOW"

    log.info(f"BTC: シグナル = {signal} ({confidence})")

    return {
        "date": date_str,
        "symbol": SYMBOL,
        "current_price": current_price,
        "rsi": rsi,
        "short_ma": ma["short_ma"],
        "long_ma": ma["long_ma"],
        "ma_cross": ma["cross_type"],
        "ma_days_since_cross": ma["days_since_cross"],
        "macd_line": macd["macd_line"],
        "macd_signal": macd["signal_line"],
        "macd_histogram": macd["histogram"],
        "bb_upper": bb["upper"],
        "bb_middle": bb["middle"],
        "bb_lower": bb["lower"],
        "bb_pct_b": bb["pct_b"],
        "tech_score": tech_score,
        "signal": signal,
        "confidence": confidence,
        "indicator_scores": indicator_scores,
        "reasons": reasons,
    }


# ------------------------------------------------------------------ メイン
def main() -> None:
    api_key = os.environ.get("GMO_API_KEY", "")
    api_secret = os.environ.get("GMO_API_SECRET", "")
    gmail_addr = os.environ.get("GMAIL_ADDRESS", "")
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD", "")
    to_addr = os.environ.get("NOTIFY_TO_ADDRESS", "")

    if not all([api_key, api_secret, gmail_addr, gmail_pass, to_addr]):
        log.error("必要な環境変数が設定されていません")
        sys.exit(1)

    now = datetime.now(JST)
    log.info(f"スクリーナー開始: {now.strftime('%Y-%m-%d %H:%M:%S JST')}")

    api = GmoApi(api_key, api_secret)

    try:
        result = generate_signal(api)
    except (GmoApiError, ValueError) as e:
        log.error(f"シグナル生成失敗: {e}")
        sys.exit(1)

    signal = result["signal"]
    if signal in ("BUY", "SELL"):
        notify_screener_signal(result, gmail_addr, gmail_pass, to_addr)
        log.info(f"{signal}シグナル — メール送信完了")
    else:
        log.info("HOLDシグナル — メール送信なし")

    log.info("スクリーナー完了")


if __name__ == "__main__":
    main()
