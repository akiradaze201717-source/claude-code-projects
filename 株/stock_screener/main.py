"""清原達郎式 日次株スクリーニングBot - メインスクリプト

使い方:
    python main.py                    # 通常実行（全銘柄取得→スクリーニング→メール送信）
    python main.py --limit 20         # 20銘柄のみ処理（テスト用）
    python main.py --no-email         # メール送信せずコンソール表示
    python main.py --fetch-only       # データ取得のみ（キャッシュ構築用）
    python main.py --screen-only      # 既存キャッシュでスクリーニングのみ
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    print("ERROR: python-dotenv が必要です。pip install python-dotenv を実行してください")
    sys.exit(1)

# スクリプトのディレクトリを基準にする
SCRIPT_DIR = Path(__file__).parent
os.chdir(SCRIPT_DIR)

from 株.stock_screener.data_fetcher import fetch_all, fetch_market_caps
from 株.stock_screener.email_sender import send_screening_email
from 株.stock_screener.screener import format_oku, screen_stocks
from 株.stock_screener.stock_list import get_stock_list

# 銀行・保険・証券はNCAV法が機能しない（負債構造が特殊）
# 不動産は固定資産が主体でNCAVが歪む
EXCLUDED_SECTORS_METHOD = {"銀行業", "保険業", "証券、商品先物取引業", "不動産業"}
# 好みで除外する業種（薄利・在庫回転型など。ユーザー指定で追加）
EXCLUDED_SECTORS_PREF = {"情報・通信業", "卸売業"}
EXCLUDED_SECTORS = EXCLUDED_SECTORS_METHOD | EXCLUDED_SECTORS_PREF


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(
                SCRIPT_DIR / "screener.log",
                encoding="utf-8",
            ),
        ],
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="清原達郎式 日次株スクリーニングBot",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="処理する銘柄数上限（テスト用）",
    )
    parser.add_argument(
        "--no-email",
        action="store_true",
        help="メール送信せずコンソールに結果を表示",
    )
    parser.add_argument(
        "--fetch-only",
        action="store_true",
        help="データ取得のみ（スクリーニング・メール送信しない）",
    )
    parser.add_argument(
        "--screen-only",
        action="store_true",
        help="既存キャッシュでスクリーニングのみ（データ取得しない）",
    )
    return parser.parse_args()


def print_results(results):
    """コンソールに結果を表示。"""
    if not results:
        print("\n該当銘柄なし")
        return

    primary_count = sum(1 for r in results if r.is_primary)
    print(
        f"\n該当: {len(results)}件（本命: {primary_count}件 / "
        f"準候補: {len(results) - primary_count}件）  ネットキャッシュ比率降順"
    )
    print("=" * 84)
    print(
        f"{'コード':>6}  {'銘柄名':<20} {'市場':<8} "
        f"{'時価総額':>8} {'NC比率':>6} {'現金比':>5} {'PER':>6} {'単元':>6}"
    )
    print("-" * 84)

    for r in results:
        flag = "[本命]" if r.is_primary else "[準]  "
        small = "★" if r.is_small_cap else " "
        name = r.name[:18] if len(r.name) > 18 else r.name
        per_str = f"{r.per:.1f}" if r.per else "  -  "
        unit_str = f"{r.unit_cost / 10000:.1f}万" if r.unit_cost else "  -  "
        print(
            f"{r.code.replace('.T', ''):>6}{small} {name:<20} {r.market:<8} "
            f"{format_oku(r.market_cap):>7}億 {r.net_cash_ratio:>5.2f} "
            f"{r.cash_ratio:>4.0%} {per_str:>6} {unit_str:>6} {flag}"
        )


def main():
    setup_logging()
    logger = logging.getLogger("main")
    args = parse_args()

    # 設定読み込み
    env_path = SCRIPT_DIR / "config.env"
    if not env_path.exists():
        logger.error("config.env が見つかりません。config.env を設定してください。")
        sys.exit(1)
    load_dotenv(env_path)

    cache_dir = os.getenv("CACHE_DIR", "./cache")
    cache_expiry = int(os.getenv("CACHE_EXPIRY_HOURS", "20"))
    stock_list_cache_days = int(os.getenv("STOCK_LIST_CACHE_DAYS", "30"))
    prefilter_cache_days = int(os.getenv("PREFILTER_CACHE_DAYS", "30"))

    start_time = time.time()

    # Step 1: 銘柄リスト取得
    logger.info("Step 1: 銘柄リスト取得")
    stocks = get_stock_list(cache_dir, stock_list_cache_days)
    logger.info("対象銘柄数: %d", len(stocks))

    # Step 1b: 業種フィルタ（APIコール不要）
    before = len(stocks)
    stocks = [s for s in stocks if s.sector not in EXCLUDED_SECTORS]
    logger.info(
        "業種フィルタ後: %d → %d銘柄（除外: %d）", before, len(stocks), before - len(stocks)
    )

    if args.screen_only:
        # キャッシュにある分だけ使い、未取得銘柄はAPIを呼ばず無視
        logger.info("Step 2: スキップ（--screen-only モード）")
        financial_data = fetch_all(
            stocks,
            cache_dir,
            cache_expiry,
            limit=args.limit,
            cache_only=True,
        )
    else:
        # Step 2: 時価総額で事前フィルタ
        logger.info("Step 2: 時価総額による事前フィルタ")
        stocks = fetch_market_caps(stocks, cache_dir, prefilter_cache_days)
        logger.info("フィルタ後の対象銘柄数: %d", len(stocks))

        # Step 3: 絞り込んだ銘柄のみフルデータ取得
        logger.info("Step 3: 財務データ取得")
        financial_data = fetch_all(
            stocks,
            cache_dir,
            cache_expiry,
            limit=args.limit,
        )

    if args.fetch_only:
        elapsed = time.time() - start_time
        logger.info("データ取得完了（--fetch-only モード）。実行時間: %.1f秒", elapsed)
        return

    # Step 4: スクリーニング
    logger.info("Step 4: スクリーニング実行")
    results = screen_stocks(financial_data)

    elapsed = time.time() - start_time
    stats = {
        "total": len(stocks) if not args.limit else args.limit,
        "fetched": sum(1 for d in financial_data if d.error is None),
        "duration": f"{elapsed:.0f}秒",
    }

    # 結果表示
    print_results(results)
    logger.info(
        "該当銘柄: %d件（本命: %d件）",
        len(results),
        sum(1 for r in results if r.is_primary),
    )

    # Step 5: メール送信
    if args.no_email:
        logger.info("メール送信スキップ（--no-email モード）")
    else:
        gmail_address = os.getenv("GMAIL_ADDRESS", "")
        gmail_password = os.getenv("GMAIL_APP_PASSWORD", "")
        recipient = os.getenv("RECIPIENT_EMAIL", gmail_address)

        if not gmail_address or not gmail_password or "your_email" in gmail_address:
            logger.error(
                "Gmail設定が未完了です。config.env の GMAIL_ADDRESS と "
                "GMAIL_APP_PASSWORD を設定してください。"
            )
            sys.exit(1)

        logger.info("Step 5: メール送信")
        send_screening_email(results, gmail_address, gmail_password, recipient, stats)

    logger.info("全処理完了。実行時間: %.1f秒", time.time() - start_time)


if __name__ == "__main__":
    main()
