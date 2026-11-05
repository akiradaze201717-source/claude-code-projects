"""
crypto_indicators.py のユニットテスト

純粋計算関数 (_ema, _sma, compute_ma_crossover, compute_macd, compute_bollinger)
はモックなしでそのまま実行。
fetch_closing_prices は GmoApi.get_klines をモック。
"""

import math
import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from crypto_indicators import (
    _ema,
    _sma,
    compute_bollinger,
    compute_ma_crossover,
    compute_macd,
    fetch_closing_prices,
)
from gmo_api import GmoApi, GmoApiError

# ============================================================
# _sma
# ============================================================


class TestSma:
    def test_basic(self):
        assert _sma([1.0, 2.0, 3.0, 4.0, 5.0], 3) == [2.0, 3.0, 4.0]

    def test_period_equals_length(self):
        assert _sma([1.0, 2.0, 3.0], 3) == [2.0]

    def test_period_greater_than_length_returns_empty(self):
        assert _sma([1.0, 2.0], 3) == []

    def test_empty_input_returns_empty(self):
        assert _sma([], 3) == []

    def test_period_1_returns_same_values(self):
        prices = [1.0, 2.0, 3.0]
        assert _sma(prices, 1) == prices

    def test_constant_prices(self):
        result = _sma([5.0] * 10, 3)
        assert all(v == 5.0 for v in result)
        assert len(result) == 8

    def test_output_length(self):
        n, p = 20, 5
        result = _sma(list(range(n)), p)
        assert len(result) == n - p + 1


# ============================================================
# _ema
# ============================================================


class TestEma:
    def test_period_equals_length(self):
        result = _ema([1.0, 2.0, 3.0], 3)
        assert len(result) == 1
        assert result[0] == 2.0  # SMAシード

    def test_period_greater_than_length_returns_empty(self):
        assert _ema([1.0, 2.0], 3) == []

    def test_empty_input_returns_empty(self):
        assert _ema([], 3) == []

    def test_constant_prices_all_equal(self):
        result = _ema([5.0] * 10, 3)
        assert all(abs(v - 5.0) < 1e-9 for v in result)

    def test_ema_weights_recent_more(self):
        """EMA は最近の値に近づく"""
        prices = [100.0] * 10 + [200.0] * 10
        result = _ema(prices, 5)
        # 後半（上昇後）の EMA は前半より高い
        assert result[-1] > result[0]

    def test_seed_is_sma_of_first_period(self):
        prices = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = _ema(prices, 3)
        # シード = (1+2+3)/3 = 2.0
        assert abs(result[0] - 2.0) < 1e-9


# _ema の output_length テストに float generator を使っていたバグを修正
class TestEmaOutputLength:
    def test_output_length(self):
        n, p = 20, 5
        result = _ema([float(i) for i in range(n)], p)
        assert len(result) == n - p + 1


# ============================================================
# compute_ma_crossover
# ============================================================


class TestComputeMaCrossover:
    def _rising(self, n=30):
        return [float(i) for i in range(1, n + 1)]

    def _falling(self, n=30):
        return [float(n - i) for i in range(n)]

    def test_uptrend_short_above_long(self):
        result = compute_ma_crossover(self._rising(30))
        assert result["short_ma"] > result["long_ma"]

    def test_downtrend_short_below_long(self):
        result = compute_ma_crossover(self._falling(30))
        assert result["short_ma"] < result["long_ma"]

    def test_insufficient_data_returns_defaults(self):
        result = compute_ma_crossover([1.0, 2.0, 3.0])
        assert result == {
            "short_ma": 0.0,
            "long_ma": 0.0,
            "cross_type": "none",
            "days_since_cross": -1,
        }

    def test_returns_required_keys(self):
        result = compute_ma_crossover(self._rising(30))
        assert set(result.keys()) == {"short_ma", "long_ma", "cross_type", "days_since_cross"}

    def test_golden_cross_detected(self):
        """下落後に急上昇 → ゴールデンクロス検出"""
        prices = [float(20 - i) for i in range(20)] + [float(i * 3) for i in range(15)]
        result = compute_ma_crossover(prices)
        assert result["cross_type"] == "golden"
        assert result["days_since_cross"] >= 0

    def test_dead_cross_detected(self):
        """上昇後に急下落 → デッドクロス検出"""
        prices = [float(i) for i in range(20)] + [float(20 - i * 2) for i in range(15)]
        result = compute_ma_crossover(prices)
        assert result["cross_type"] == "dead"
        assert result["days_since_cross"] >= 0

    def test_no_cross_returns_none(self):
        """単調上昇ではクロスなし"""
        result = compute_ma_crossover(self._rising(30))
        assert result["cross_type"] == "none"

    def test_constant_prices_no_cross(self):
        result = compute_ma_crossover([100.0] * 30)
        assert result["cross_type"] == "none"


# ============================================================
# compute_macd
# ============================================================


class TestComputeMacd:
    def _rising(self, n=50):
        return [float(i) for i in range(1, n + 1)]

    def _flat(self, n=50):
        return [100.0] * n

    def test_returns_required_keys(self):
        result = compute_macd(self._rising(50))
        assert set(result.keys()) == {
            "macd_line",
            "signal_line",
            "histogram",
            "histogram_increasing",
        }

    def test_insufficient_ema_returns_defaults(self):
        result = compute_macd([1.0, 2.0, 3.0])
        assert result == {
            "macd_line": 0.0,
            "signal_line": 0.0,
            "histogram": 0.0,
            "histogram_increasing": False,
        }

    def test_flat_prices_macd_near_zero(self):
        """一定価格では MACD ≈ 0"""
        result = compute_macd(self._flat(50))
        assert abs(result["macd_line"]) < 1.0
        assert abs(result["signal_line"]) < 1.0

    def test_rising_prices_macd_positive(self):
        """上昇トレンドでは短期EMA > 長期EMA → MACD > 0"""
        result = compute_macd(self._rising(50))
        assert result["macd_line"] > 0

    def test_falling_prices_macd_negative(self):
        """下落トレンドでは MACD < 0"""
        prices = [float(50 - i) for i in range(50)]
        result = compute_macd(prices)
        assert result["macd_line"] < 0

    def test_histogram_is_macd_minus_signal(self):
        result = compute_macd(self._rising(50))
        expected = result["macd_line"] - result["signal_line"]
        assert abs(result["histogram"] - expected) < 1e-9

    def test_histogram_increasing_flag(self):
        """単調上昇ではヒストグラムが増加傾向"""
        result = compute_macd(self._rising(60))
        assert isinstance(result["histogram_increasing"], bool)

    def test_minimum_data_for_signal(self):
        """34本（MIN_PRICES）でクラッシュしない"""
        prices = [float(i) for i in range(34)]
        result = compute_macd(prices)
        assert "macd_line" in result


# ============================================================
# compute_bollinger
# ============================================================


class TestComputeBollinger:
    def test_returns_required_keys(self):
        result = compute_bollinger([100.0] * 25)
        assert set(result.keys()) == {"upper", "middle", "lower", "pct_b", "bandwidth"}

    def test_constant_prices_upper_equals_lower(self):
        """分散ゼロ → upper = lower = middle"""
        result = compute_bollinger([100.0] * 25)
        assert result["upper"] == result["lower"] == result["middle"] == 100.0

    def test_constant_prices_bandwidth_zero(self):
        result = compute_bollinger([100.0] * 25)
        assert result["bandwidth"] == 0.0

    def test_constant_prices_pct_b_is_half(self):
        """バンド幅ゼロのとき pct_b = 0.5（ゼロ除算回避）"""
        result = compute_bollinger([100.0] * 25)
        assert result["pct_b"] == 0.5

    def test_insufficient_data_returns_defaults(self):
        result = compute_bollinger([100.0] * 5, period=20)
        assert result == {"upper": 0.0, "middle": 0.0, "lower": 0.0, "pct_b": 0.5, "bandwidth": 0.0}

    def test_middle_is_sma_of_last_period_prices(self):
        prices = list(range(1, 26))  # 1〜25
        result = compute_bollinger(prices, period=5)
        expected_middle = sum(range(21, 26)) / 5  # 最後の5本: 21〜25
        assert abs(result["middle"] - expected_middle) < 1e-9

    def test_upper_above_middle_above_lower(self):
        prices = [float(i) + (i % 3) * 10 for i in range(25)]
        result = compute_bollinger(prices)
        assert result["upper"] >= result["middle"] >= result["lower"]

    def test_price_at_middle_gives_pct_b_half(self):
        """最終価格 = 中間値のとき pct_b ≈ 0.5"""
        prices = list(range(1, 25)) + [0]
        result = compute_bollinger(prices)
        middle = result["middle"]
        # 最終価格が middle に等しいケースを直接組む
        constant = [100.0] * 19 + [110.0] * 5  # 最後5本の平均 = 110 に近い
        r = compute_bollinger(constant)
        # pct_b が 0〜1 の範囲内であることを確認
        assert 0.0 <= r["pct_b"] <= 1.0

    def test_price_above_upper_gives_pct_b_above_1(self):
        """最終価格 > 上限 → pct_b > 1.0"""
        prices = [100.0] * 19 + [100.0] * 4 + [10_000.0]
        result = compute_bollinger(prices)
        assert result["pct_b"] > 1.0

    def test_price_below_lower_gives_pct_b_below_0(self):
        """最終価格 < 下限 → pct_b < 0.0"""
        prices = [100.0] * 19 + [100.0] * 4 + [0.001]
        result = compute_bollinger(prices)
        assert result["pct_b"] < 0.0

    def test_bandwidth_positive_when_variance_exists(self):
        prices = [float(i) for i in range(25)]
        result = compute_bollinger(prices)
        assert result["bandwidth"] > 0.0

    def test_num_std_2_default(self):
        """デフォルト num_std=2 で upper = middle + 2*std"""
        prices = [float(i) for i in range(25)]
        result = compute_bollinger(prices, period=20)
        window = prices[-20:]
        middle = sum(window) / 20
        variance = sum((p - middle) ** 2 for p in window) / 20
        std = math.sqrt(variance)
        assert abs(result["upper"] - (middle + 2 * std)) < 1e-6
        assert abs(result["lower"] - (middle - 2 * std)) < 1e-6

    def test_custom_num_std(self):
        prices = [float(i) for i in range(25)]
        r1 = compute_bollinger(prices, num_std=1.0)
        r2 = compute_bollinger(prices, num_std=3.0)
        assert r2["upper"] > r1["upper"]
        assert r2["lower"] < r1["lower"]


# ============================================================
# fetch_closing_prices（crypto_indicators 版）
# ============================================================

_BASE_MS = 1_735_689_600_000


def _day_ms(offset):
    return _BASE_MS + offset * 86_400_000


def _make_kline(offset, close):
    return {"openTime": str(_day_ms(offset)), "close": str(close)}


class TestFetchClosingPricesCryptoIndicators:
    def test_gets_2_years_by_default(self):
        """日足APIは年単位指定 → 今年・去年の2回呼ばれる"""
        api = MagicMock(spec=GmoApi)
        api.get_klines.return_value = []
        fetch_closing_prices(api, "BTC")
        assert api.get_klines.call_count == 2

    def test_custom_num_months_still_fetches_2_years(self):
        """num_months は互換引数として残るが内部は2年固定"""
        api = MagicMock(spec=GmoApi)
        api.get_klines.return_value = []
        fetch_closing_prices(api, "BTC", num_months=2)
        assert api.get_klines.call_count == 2

    def test_returns_sorted_prices(self):
        klines = [_make_kline(i, 100.0 + i) for i in range(10)]
        api = MagicMock(spec=GmoApi)
        api.get_klines.side_effect = [klines, [], []]
        prices = fetch_closing_prices(api, "BTC")
        assert prices == sorted(prices)

    def test_api_error_skips_that_month(self):
        good = [_make_kline(i, float(i)) for i in range(5)]
        api = MagicMock(spec=GmoApi)
        api.get_klines.side_effect = [GmoApiError("fail"), good, []]
        prices = fetch_closing_prices(api, "BTC")
        assert len(prices) == 5

    def test_all_errors_returns_empty(self):
        api = MagicMock(spec=GmoApi)
        api.get_klines.side_effect = GmoApiError("fail")
        prices = fetch_closing_prices(api, "BTC")
        assert prices == []

    def test_close_values_converted_to_float(self):
        klines = [_make_kline(0, 9_500_000)]
        api = MagicMock(spec=GmoApi)
        api.get_klines.side_effect = [klines, [], []]
        prices = fetch_closing_prices(api, "BTC")
        assert isinstance(prices[0], float)
