"""yfinance財務データ取得モジュール（レート制限・キャッシュ付き）"""

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from dataclasses import fields as dataclass_fields
from datetime import datetime, timedelta
from pathlib import Path

try:
    import yfinance as yf
except ImportError:
    print("ERROR: yfinance が必要です。pip install yfinance を実行してください")
    raise

from 株.stock_screener.stock_list import StockInfo

logger = logging.getLogger(__name__)

# --- 定数 ---
MAX_RETRIES = 3
INITIAL_BACKOFF = 30
DELAY_MARKET_CAP_FETCH = 0.5
DELAY_BETWEEN_TICKERS = 0.5  # 並列取得時の1スレッドあたり待機時間
PARALLEL_WORKERS = 3  # 本取得の初期並列数（バランスシートあり・重い）
PREFILTER_WORKERS = 5  # 事前フィルタの初期並列数（info取得のみ・軽い）
PARALLEL_MAX = 8  # 並列数の上限
PARALLEL_MIN = 1  # 並列数の下限
INCREASE_AFTER = 20  # 連続成功N件で並列数+1


class AdaptiveWorkers:
    """429エラーで並列数-1、連続成功でN件ごとに+1する自動調整クラス。"""

    def __init__(self, initial: int, min_w: int = PARALLEL_MIN, max_w: int = PARALLEL_MAX):
        self._count = initial
        self._min = min_w
        self._max = max_w
        self._sem = threading.Semaphore(initial)
        self._lock = threading.Lock()
        self._successes = 0

    @property
    def count(self) -> int:
        return self._count

    def acquire(self) -> None:
        self._sem.acquire()

    def on_success(self) -> None:
        with self._lock:
            self._successes += 1
            if self._successes >= INCREASE_AFTER and self._count < self._max:
                self._count += 1
                self._successes = 0
                logger.info("並列数を %d に増加", self._count)
                self._sem.release()  # 通常解放 + 追加スロット
                self._sem.release()
            else:
                self._sem.release()

    def on_rate_limit(self) -> None:
        with self._lock:
            self._successes = 0
            if self._count > self._min:
                self._count -= 1
                logger.info("429検知: 並列数を %d に削減", self._count)
                # 解放しない → スロットを1つ消費してデッドロック防止のため現在値維持
            else:
                self._sem.release()  # 最小値のため通常解放


MARKET_CAP_MAX = 50_000_000_000  # 500億円（清原基準: 割安小型）
MARKET_CAP_MIN = 500_000_000  # 5億円（ボロ株・整理銘柄の下限）
PER_MAX = 15.0  # 後方互換用（screener側は PER_KIYO_MAX を使用）
PREFILTER_PER_MAX = 12.0  # 事前フィルタでのPER上限（最終基準10 + バッファ）
PRICE_MIN = 50.0  # 整理銘柄・ボロ株除外（円）
DE_MAX = 300.0  # 負債資本倍率上限（300% = 3倍）

# 清原ネットキャッシュの「投資有価証券」に相当するBS科目候補（yfinance）
INV_SECURITIES_KEYS = [
    "Investmentin Financial Assets",
    "Available For Sale Securities",
    "Long Term Equity Investment",
    "Investments And Advances",
]


@dataclass
class FinancialData:
    code: str
    name: str
    market: str
    sector: str
    fetched_at: str
    market_cap: float | None = None
    current_price: float | None = None
    trailing_pe: float | None = None
    current_assets: float | None = None
    total_liabilities: float | None = None
    cash_and_equivalents: float | None = None
    investment_securities: float | None = None  # 投資有価証券（清原式で×70%評価）
    debt_to_equity: float | None = None
    error: str | None = None


def fetch_market_caps(
    stocks: list[StockInfo],
    cache_dir: str,
    cache_days: int = 30,
) -> list[StockInfo]:
    """事前フィルタを適用し、候補銘柄のみ返す。

    除外条件:
      - 時価総額 < 5億円 または > 500億円
      - 株価 < 50円
      - D/E比率 > 300%
      - PER >= 15
      - グロース市場 かつ PERなし（赤字）

    バランスシートは取得しないため高速。キャッシュ済み銘柄は
    既存キャッシュから値を読み取り、API呼び出しをスキップする。
    除外と判定した銘柄もキャッシュに保存し、次回の再取得を防ぐ。
    """
    fin_cache_dir = Path(cache_dir) / "financials"
    fin_cache_dir.mkdir(parents=True, exist_ok=True)

    filtered = []
    to_check = []

    for stock in stocks:
        cached = _load_cache(fin_cache_dir, stock.code, expiry_hours=cache_days * 24)
        if cached and cached.market_cap is not None:
            if not _prefilter_reject(
                cached.market_cap,
                cached.trailing_pe,
                stock.market,
                cached.current_price,
                cached.debt_to_equity,
            ):
                filtered.append(stock)
        else:
            to_check.append(stock)

    logger.info(
        "事前フィルタ: キャッシュ済み%d件 / 新規取得%d件",
        len(stocks) - len(to_check),
        len(to_check),
    )

    if to_check:
        aw = AdaptiveWorkers(initial=PREFILTER_WORKERS)
        prefilter_lock = threading.Lock()
        prefilter_passed = []
        prefilter_done = [0]

        def check_one(stock: StockInfo) -> None:
            aw.acquire()
            time.sleep(DELAY_MARKET_CAP_FETCH)
            try:
                info = yf.Ticker(stock.code).info or {}
                cap = _to_float(info.get("marketCap"))
                per = _to_float(info.get("trailingPE"))
                price = _to_float(info.get("currentPrice") or info.get("regularMarketPrice"))
                de = _to_float(info.get("debtToEquity"))
                rejected = _prefilter_reject(cap, per, stock.market, price, de)
                with prefilter_lock:
                    prefilter_done[0] += 1
                    if prefilter_done[0] % 200 == 0 or prefilter_done[0] == len(to_check):
                        logger.info(
                            "事前フィルタ進捗: %d/%d件完了 (並列数:%d)",
                            prefilter_done[0],
                            len(to_check),
                            aw.count,
                        )
                    if rejected:
                        _save_cache(
                            fin_cache_dir,
                            FinancialData(
                                code=stock.code,
                                name=stock.name,
                                market=stock.market,
                                sector=stock.sector,
                                fetched_at=datetime.now().isoformat(),
                                market_cap=cap,
                                current_price=price,
                                trailing_pe=per,
                                debt_to_equity=de,
                            ),
                        )
                    else:
                        prefilter_passed.append(stock)
                aw.on_success()
            except Exception as e:
                if "429" in str(e) or "Too Many Requests" in str(e):
                    aw.on_rate_limit()
                else:
                    logger.debug("%s: 事前フィルタ取得失敗 - %s", stock.code, e)
                    aw.on_success()  # 429以外は無視して継続

        logger.info("%d並列で事前フィルタ取得開始...", PREFILTER_WORKERS)
        with ThreadPoolExecutor(max_workers=PARALLEL_MAX) as executor:
            list(executor.map(check_one, to_check))

        filtered.extend(prefilter_passed)

    logger.info(
        "事前フィルタ完了: %d/%d銘柄が通過",
        len(filtered),
        len(stocks),
    )
    return filtered


def _to_float(value) -> float | None:
    """str/int/float を float に変換。変換不能なら None。"""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _prefilter_reject(market_cap, per, market: str = "", price=None, de=None) -> bool:
    """事前フィルタで除外すべきならTrueを返す。"""
    market_cap = _to_float(market_cap)
    per = _to_float(per)
    price = _to_float(price)
    de = _to_float(de)

    if price is not None and price < PRICE_MIN:
        return True
    if de is not None and de > DE_MAX:
        return True
    if market == "グロース" and per is None:
        return True
    if per is not None and per >= PREFILTER_PER_MAX:
        return True
    if market_cap is None or market_cap <= 0:
        return False  # 時価総額不明は通す
    if market_cap < MARKET_CAP_MIN:
        return True
    if market_cap > MARKET_CAP_MAX:
        return True
    return False


def fetch_all(
    stocks: list[StockInfo],
    cache_dir: str,
    cache_expiry_hours: int = 20,
    limit: int | None = None,
    cache_only: bool = False,
) -> list[FinancialData]:
    """全銘柄の財務データを取得（キャッシュ活用）。

    cache_only=True のとき、キャッシュにない銘柄はAPIを呼ばず無視する。
    """
    fin_cache_dir = Path(cache_dir) / "financials"
    fin_cache_dir.mkdir(parents=True, exist_ok=True)

    if limit:
        stocks = stocks[:limit]

    total = len(stocks)
    results = []
    to_fetch = []

    for stock in stocks:
        cached = _load_cache(fin_cache_dir, stock.code, cache_expiry_hours)
        if cached:
            results.append(cached)
        else:
            to_fetch.append(stock)

    if cache_only:
        logger.info(
            "キャッシュヒット: %d/%d銘柄（--screen-only: 未取得%d銘柄はスキップ）",
            len(results),
            total,
            len(to_fetch),
        )
        return results

    logger.info(
        "キャッシュヒット: %d/%d銘柄、新規取得: %d銘柄",
        len(results),
        total,
        len(to_fetch),
    )

    if not to_fetch:
        return results

    aw = AdaptiveWorkers(initial=PARALLEL_WORKERS)
    cache_lock = threading.Lock()
    done_count = [0]

    def fetch_and_cache(stock: StockInfo) -> FinancialData:
        aw.acquire()
        time.sleep(DELAY_BETWEEN_TICKERS)
        data = _fetch_single(stock)
        is_rate_limit = data.error and "レート制限" in data.error
        with cache_lock:
            _save_cache(fin_cache_dir, data)
            done_count[0] += 1
            if done_count[0] % 50 == 0 or done_count[0] == len(to_fetch):
                logger.info(
                    "取得進捗: %d/%d銘柄完了 (並列数:%d)",
                    done_count[0],
                    len(to_fetch),
                    aw.count,
                )
        if is_rate_limit:
            aw.on_rate_limit()
        else:
            aw.on_success()  # 429以外のエラーも無視して継続
        return data

    logger.info("%d並列で%d銘柄を取得開始...", PARALLEL_WORKERS, len(to_fetch))
    with ThreadPoolExecutor(max_workers=PARALLEL_MAX) as executor:
        futures = {executor.submit(fetch_and_cache, stock): stock for stock in to_fetch}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                stock = futures[future]
                logger.warning("%s: 並列取得で予期しないエラー - %s", stock.code, e)

    fetched_ok = sum(1 for d in results if d.error is None)
    logger.info("データ取得完了: %d/%d銘柄成功", fetched_ok, total)
    return results


def _fetch_single(stock: StockInfo) -> FinancialData:
    """1銘柄のデータを取得（リトライ付き）。"""
    data = FinancialData(
        code=stock.code,
        name=stock.name,
        market=stock.market,
        sector=stock.sector,
        fetched_at=datetime.now().isoformat(),
    )

    backoff = INITIAL_BACKOFF
    for attempt in range(MAX_RETRIES):
        try:
            ticker = yf.Ticker(stock.code)
            info = ticker.info or {}

            data.market_cap = info.get("marketCap")
            data.trailing_pe = info.get("trailingPE")
            data.current_price = _to_float(
                info.get("currentPrice") or info.get("regularMarketPrice")
            )

            bs = ticker.balance_sheet
            if bs is None or bs.empty:
                bs = ticker.quarterly_balance_sheet

            if bs is not None and not bs.empty:
                latest = bs.iloc[:, 0]
                data.current_assets = _get_bs_value(
                    latest,
                    [
                        "Current Assets",
                        "CurrentAssets",
                        "Total Current Assets",
                    ],
                )
                data.total_liabilities = _get_bs_value(
                    latest,
                    [
                        "Total Liabilities Net Minority Interest",
                        "Total Liabilities",
                        "TotalLiabilitiesNetMinorityInterest",
                    ],
                )
                data.cash_and_equivalents = _get_bs_value(
                    latest,
                    [
                        "Cash And Cash Equivalents",
                        "CashAndCashEquivalents",
                        "Cash Cash Equivalents And Short Term Investments",
                    ],
                )
                data.investment_securities = _get_bs_value(latest, INV_SECURITIES_KEYS)

            if data.current_assets is None:
                data.current_assets = info.get("totalCurrentAssets")
            if data.total_liabilities is None:
                data.total_liabilities = info.get("totalDebt")
            if data.cash_and_equivalents is None:
                data.cash_and_equivalents = info.get("totalCash")

            return data

        except Exception as e:
            error_msg = str(e)
            is_rate_limit = "429" in error_msg or "Too Many Requests" in error_msg
            if is_rate_limit and attempt < MAX_RETRIES - 1:
                logger.warning(
                    "%s: レート制限 (429)。%d秒後にリトライ (%d/%d)...",
                    stock.code,
                    backoff,
                    attempt + 1,
                    MAX_RETRIES,
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, 300)
                continue
            data.error = (
                "レート制限により取得失敗（リトライ上限）"
                if is_rate_limit
                else f"{type(e).__name__}: {error_msg}"
            )
            logger.warning("%s: データ取得失敗 - %s", stock.code, data.error)
            return data

    # 到達しないが安全のため
    data.error = "予期しないリトライ終了"
    return data


def _get_bs_value(series, keys: list[str]) -> float | None:
    for key in keys:
        if key in series.index:
            val = series[key]
            if val is not None and str(val) != "nan":
                return float(val)
    return None


def _cache_path(cache_dir: Path, code: str) -> Path:
    safe_code = code.replace(".", "_")
    return cache_dir / f"{safe_code}.json"


def _load_cache(cache_dir: Path, code: str, expiry_hours: int) -> FinancialData | None:
    path = _cache_path(cache_dir, code)
    if not path.exists():
        return None

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        fetched_at = datetime.fromisoformat(raw["fetched_at"])
        if datetime.now() - fetched_at > timedelta(hours=expiry_hours):
            return None
        # 既知フィールドのみ渡す（フィールド追加・削除後のキャッシュ互換性）
        known = {f.name for f in dataclass_fields(FinancialData)}
        return FinancialData(**{k: v for k, v in raw.items() if k in known})
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def _save_cache(cache_dir: Path, data: FinancialData) -> None:
    path = _cache_path(cache_dir, data.code)
    path.write_text(
        json.dumps(asdict(data), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
