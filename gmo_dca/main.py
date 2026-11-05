"""
スマートDCA自動積立システム — GMO Coin
毎月16日〜月末にBTC/ETHを成行購入。RSIで購入額を調整。
"""

import logging
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from gmo_api import GmoApi, GmoApiError

load_dotenv(Path(__file__).parent / "config.env")
from log_setup import setup_logger
from notifier import (
    notify_already_purchased,
    notify_balance_insufficient,
    notify_error,
    notify_purchase,
    notify_rsi_skip,
)
from rsi import get_rsi

# ------------------------------------------------------------------ 定数
JST = timezone(timedelta(hours=9))

COINS = [
    # (シンボル, 小数桁数, 最小数量)
    ("BTC", 4, 0.0001),
    ("ETH", 2, 0.01),
]

BUDGET_NORMAL = 5000  # RSI 30-70
BUDGET_BOOST = 7500  # RSI < 30
RSI_HIGH = 70.0
RSI_LOW = 30.0

setup_logger("dca.log")
log = logging.getLogger(__name__)


# ------------------------------------------------------------------ ヘルパー
def floor_quantity(value: float, decimals: int) -> float:
    """指定小数桁で切り捨て。"""
    factor = 10**decimals
    return math.floor(value * factor) / factor


def get_month_16th(now: datetime) -> datetime:
    """当月16日 00:00:00 JST を UTC aware で返す。"""
    return datetime(now.year, now.month, 16, tzinfo=JST)


# ------------------------------------------------------------------ メイン
def process_coin(
    api: GmoApi,
    symbol: str,
    decimals: int,
    min_qty: float,
    since: datetime,
    gmail_addr: str,
    gmail_pass: str,
    to_addr: str,
) -> None:
    """1銘柄分の処理。"""

    # 1. 二重購入チェック（APIエラーは例外伝播 → 呼び出し元で中断）
    log.info(f"{symbol}: 約定履歴チェック中...")
    if api.has_bought_since(symbol, since):
        log.info(f"{symbol}: 当月購入済み — スキップ")
        notify_already_purchased(symbol, gmail_addr, gmail_pass, to_addr)
        return

    # 2. RSI 算出
    log.info(f"{symbol}: RSI算出中...")
    try:
        rsi = get_rsi(api, symbol)
    except (GmoApiError, ValueError) as e:
        log.warning(f"{symbol}: RSI算出失敗 — {e}")
        notify_error(f"{symbol} RSI算出失敗: {e}", gmail_addr, gmail_pass, to_addr)
        return
    log.info(f"{symbol}: RSI(14) = {rsi:.1f}")

    # 3. RSI判定
    if rsi >= RSI_HIGH:
        log.info(f"{symbol}: RSI {rsi:.1f} ≥ {RSI_HIGH} — スキップ")
        notify_rsi_skip(symbol, rsi, gmail_addr, gmail_pass, to_addr)
        return

    budget = BUDGET_BOOST if rsi < RSI_LOW else BUDGET_NORMAL
    log.info(f"{symbol}: 予算 ¥{budget:,}（RSI={rsi:.1f}）")

    # 4. 残高チェック
    log.info(f"{symbol}: 残高確認中...")
    try:
        available = api.get_available_amount()
    except GmoApiError as e:
        log.warning(f"{symbol}: 残高取得失敗 — {e}")
        notify_error(f"{symbol} 残高取得失敗: {e}", gmail_addr, gmail_pass, to_addr)
        return

    if available < budget:
        log.info(f"{symbol}: 残高不足 ¥{available:,.0f} < ¥{budget:,}")
        notify_balance_insufficient(symbol, budget, available, gmail_addr, gmail_pass, to_addr)
        return

    # 5. 現在価格取得 → 数量算出
    log.info(f"{symbol}: Ticker取得中...")
    try:
        ticker = api.get_ticker(symbol)
    except GmoApiError as e:
        log.warning(f"{symbol}: Ticker取得失敗 — {e}")
        notify_error(f"{symbol} Ticker取得失敗: {e}", gmail_addr, gmail_pass, to_addr)
        return

    price = float(ticker.get("last", 0))
    if price <= 0:
        log.warning(f"{symbol}: 価格が無効 ({price})")
        notify_error(f"{symbol} 価格が無効: {price}", gmail_addr, gmail_pass, to_addr)
        return

    qty = floor_quantity(budget / price, decimals)
    if qty < min_qty:
        log.info(f"{symbol}: 数量 {qty} < 最小 {min_qty} — スキップ")
        notify_balance_insufficient(symbol, budget, available, gmail_addr, gmail_pass, to_addr)
        return

    size = f"{qty:.{decimals}f}"
    log.info(f"{symbol}: 成行買い {size} @ 約¥{price:,.0f}")

    # 6. 注文
    try:
        result = api.place_market_buy(symbol, size)
    except GmoApiError as e:
        log.error(f"{symbol}: 注文失敗 — {e}")
        notify_error(f"{symbol} 注文失敗: {e}", gmail_addr, gmail_pass, to_addr)
        return

    log.info(f"{symbol}: 注文成功 — {result}")
    notify_purchase(symbol, size, price, budget, rsi, gmail_addr, gmail_pass, to_addr)


def main() -> None:
    # 環境変数ロード
    api_key = os.environ.get("GMO_API_KEY", "")
    api_secret = os.environ.get("GMO_API_SECRET", "")
    gmail_addr = os.environ.get("GMAIL_ADDRESS", "")
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD", "")
    to_addr = os.environ.get("NOTIFY_TO_ADDRESS", "")

    if not all([api_key, api_secret, gmail_addr, gmail_pass, to_addr]):
        log.error("必要な環境変数が設定されていません")
        sys.exit(1)

    now = datetime.now(JST)
    log.info(f"実行開始: {now.strftime('%Y-%m-%d %H:%M:%S JST')}")

    # 日付チェック: 16日未満は購入ウィンドウ外
    if now.day < 16:
        log.info("16日未満 — 購入ウィンドウ外。終了。")
        return

    since = get_month_16th(now)
    api = GmoApi(api_key, api_secret)

    for symbol, decimals, min_qty in COINS:
        try:
            process_coin(api, symbol, decimals, min_qty, since, gmail_addr, gmail_pass, to_addr)
        except GmoApiError as e:
            # 約定履歴API失敗 → 安全のため即座に終了
            log.critical(f"{symbol}: 約定履歴確認でエラー — 安全のため処理中断: {e}")
            notify_error(
                f"{symbol} 約定履歴確認エラー（安全のため全処理中断）: {e}",
                gmail_addr,
                gmail_pass,
                to_addr,
            )
            sys.exit(1)
        except Exception as e:
            log.error(f"{symbol}: 予期しないエラー — {e}")
            notify_error(f"{symbol} 予期しないエラー: {e}", gmail_addr, gmail_pass, to_addr)
            sys.exit(1)

    log.info("全処理完了")


if __name__ == "__main__":
    main()
