"""
rsi.py のユニットテスト

- compute_rsi: 純粋関数なのでモックなし
- fetch_closing_prices: GmoApi.get_klines をモック
- get_rsi: fetch_closing_prices + compute_rsi の連携
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gmo_api import GmoApi, GmoApiError
from rsi import compute_rsi, fetch_closing_prices, get_rsi

# ============================================================
# compute_rsi — 純粋計算関数（モックなし）
# ============================================================


class TestComputeRsi:
    # --- 基本動作 ---

    def test_all_gains_returns_100(self):
        """全日上昇 → avg_loss=0 → RSI=100.0"""
        prices = [100.0 + i for i in range(20)]
        assert compute_rsi(prices) == 100.0

    def test_all_losses_returns_0(self):
        """全日下落 → avg_gain=0 → RS=0 → RSI=0.0"""
        prices = [100.0 - i for i in range(20)]
        assert compute_rsi(prices) == 0.0

    def test_flat_prices_returns_100(self):
        """全日同値 → gains=losses=0 → avg_loss=0 → RSI=100.0"""
        prices = [100.0] * 20
        assert compute_rsi(prices) == 100.0

    def test_result_in_valid_range(self):
        """RSI は常に 0〜100 の範囲に収まる"""
        import random

        random.seed(42)
        prices = [100.0 + random.gauss(0, 5) for _ in range(30)]
        rsi = compute_rsi(prices)
        assert 0.0 <= rsi <= 100.0

    def test_known_value_alternating(self):
        """上下交互の価格: 計算結果が中立付近（40〜60）になる"""
        prices = [100.0 if i % 2 == 0 else 101.0 for i in range(30)]
        rsi = compute_rsi(prices)
        assert 40.0 <= rsi <= 60.0

    # --- 境界値 ---

    def test_minimum_data_length_succeeds(self):
        """ちょうど period+1=15 本で計算できる"""
        prices = list(range(1, 16))  # 1〜15
        rsi = compute_rsi(prices)
        assert 0.0 <= rsi <= 100.0

    def test_exactly_period_raises_value_error(self):
        """period(14) 個以下はエラー"""
        prices = list(range(1, 15))  # 14個
        with pytest.raises(ValueError, match="最低15個"):
            compute_rsi(prices)

    def test_too_few_data_raises_value_error(self):
        prices = [100.0, 101.0, 99.0]
        with pytest.raises(ValueError):
            compute_rsi(prices)

    def test_empty_list_raises_value_error(self):
        with pytest.raises(ValueError):
            compute_rsi([])

    def test_large_dataset_does_not_raise(self):
        """100本でも正常動作する"""
        prices = [100.0 + i * 0.5 for i in range(100)]
        rsi = compute_rsi(prices)
        assert 0.0 <= rsi <= 100.0

    # --- カスタム period ---

    def test_custom_period_7(self):
        prices = list(range(1, 20))  # 上昇
        rsi = compute_rsi(prices, period=7)
        assert rsi == 100.0

    def test_custom_period_too_large_raises(self):
        prices = [100.0] * 5
        with pytest.raises(ValueError):
            compute_rsi(prices, period=10)

    # --- Wilder's Smoothing の性質 ---

    def test_wilder_smoothing_dampens_single_spike(self):
        """上下の履歴がある中での1回の急騰は RSI を 100 にしない（平滑化の効果）"""
        # 上下交互の履歴（avg_loss > 0 を作る）の後に急騰
        prices = [100.0 if i % 2 == 0 else 99.0 for i in range(20)]
        prices.append(200.0)  # 最後だけ急騰
        rsi = compute_rsi(prices)
        assert rsi < 100.0

    def test_sustained_rise_gives_higher_rsi_than_sustained_fall(self):
        rising = [100.0 + i for i in range(20)]
        falling = [200.0 - i for i in range(20)]
        assert compute_rsi(rising) > compute_rsi(falling)


# ============================================================
# fetch_closing_prices — GmoApi.get_klines をモック
# ============================================================


def _make_kline(open_time_ms: int, close: float) -> dict:
    return {"openTime": str(open_time_ms), "close": str(close)}


def _make_api_with_klines(month_data: dict[str, list[dict]]) -> MagicMock:
    """get_klines(symbol, date_str) の戻り値を date_str でルーティングするモック。"""
    api = MagicMock(spec=GmoApi)

    def side_effect(symbol, date_str):
        for key, klines in month_data.items():
            if key in date_str:
                return klines
        return []

    api.get_klines.side_effect = side_effect
    return api


# 固定の openTime: 2025-01-01〜 の1日ずつ（ミリ秒）
_BASE_MS = 1_735_689_600_000  # 2025-01-01 00:00:00 UTC


def _day_ms(offset: int) -> int:
    return _BASE_MS + offset * 86_400_000


class TestFetchClosingPrices:
    def test_returns_sorted_closing_prices(self):
        """2ヶ月分のデータを日付昇順で返す"""
        klines_month1 = [_make_kline(_day_ms(i), 100.0 + i) for i in range(10)]
        klines_month2 = [_make_kline(_day_ms(20 + i), 200.0 + i) for i in range(5)]
        api = MagicMock(spec=GmoApi)
        api.get_klines.side_effect = [klines_month1, klines_month2]

        prices = fetch_closing_prices(api, "BTC")

        assert len(prices) == 15
        assert prices[0] < prices[-1]  # 昇順

    def test_one_month_api_error_returns_other_month(self):
        """一方の月でAPIエラー → もう一方のデータだけ返す"""
        good_klines = [_make_kline(_day_ms(i), 100.0 + i) for i in range(5)]
        api = MagicMock(spec=GmoApi)
        api.get_klines.side_effect = [GmoApiError("fail"), good_klines]

        prices = fetch_closing_prices(api, "BTC")

        assert len(prices) == 5

    def test_both_months_api_error_returns_empty(self):
        api = MagicMock(spec=GmoApi)
        api.get_klines.side_effect = GmoApiError("fail")

        prices = fetch_closing_prices(api, "BTC")

        assert prices == []

    def test_get_klines_called_twice(self):
        """今月と先月の2回 get_klines が呼ばれる"""
        api = MagicMock(spec=GmoApi)
        api.get_klines.return_value = []

        fetch_closing_prices(api, "BTC")

        assert api.get_klines.call_count == 2

    def test_symbol_passed_correctly(self):
        api = MagicMock(spec=GmoApi)
        api.get_klines.return_value = []

        fetch_closing_prices(api, "ETH")

        for call_args in api.get_klines.call_args_list:
            assert call_args[0][0] == "ETH"

    def test_duplicate_dates_overwritten(self):
        """同じ日のデータが2回来た場合、後のデータで上書きされる"""
        same_day_ms = _day_ms(0)
        klines = [
            _make_kline(same_day_ms, 100.0),
            _make_kline(same_day_ms, 999.0),  # 同日・後の値
        ]
        api = MagicMock(spec=GmoApi)
        api.get_klines.side_effect = [klines, []]

        prices = fetch_closing_prices(api, "BTC")

        assert prices == [999.0]

    def test_close_values_are_float(self):
        """close は str で来るが float に変換される"""
        klines = [_make_kline(_day_ms(0), 9_500_000.0)]
        api = MagicMock(spec=GmoApi)
        api.get_klines.side_effect = [klines, []]

        prices = fetch_closing_prices(api, "BTC")

        assert isinstance(prices[0], float)
        assert prices[0] == 9_500_000.0


# ============================================================
# get_rsi — fetch_closing_prices + compute_rsi の連携
# ============================================================


class TestGetRsi:
    def test_returns_float(self):
        prices = [100.0 + i for i in range(20)]
        with patch("rsi.fetch_closing_prices", return_value=prices):
            api = MagicMock(spec=GmoApi)
            result = get_rsi(api, "BTC")
        assert isinstance(result, float)

    def test_delegates_to_compute_rsi(self):
        """fetch_closing_prices の戻り値が compute_rsi に渡される"""
        prices = list(range(1, 21))
        with patch("rsi.fetch_closing_prices", return_value=prices) as mock_fetch:
            api = MagicMock(spec=GmoApi)
            get_rsi(api, "ETH")
        mock_fetch.assert_called_once_with(api, "ETH")

    def test_propagates_value_error_on_insufficient_data(self):
        """データ不足の場合 ValueError が伝播する"""
        with patch("rsi.fetch_closing_prices", return_value=[100.0] * 5):
            api = MagicMock(spec=GmoApi)
            with pytest.raises(ValueError):
                get_rsi(api, "BTC")

    def test_propagates_gmo_api_error(self):
        """APIエラーが伝播する"""
        with patch("rsi.fetch_closing_prices", side_effect=GmoApiError("fail")):
            api = MagicMock(spec=GmoApi)
            with pytest.raises(GmoApiError):
                get_rsi(api, "BTC")

    def test_all_rising_prices_gives_rsi_100(self):
        prices = [100.0 + i for i in range(20)]
        with patch("rsi.fetch_closing_prices", return_value=prices):
            api = MagicMock(spec=GmoApi)
            rsi = get_rsi(api, "BTC")
        assert rsi == 100.0
