"""
main.py のユニットテスト

外部通信なし:
  - GmoApi._request はモック
  - smtplib.SMTP はモック
  - 純粋計算関数 (_score_*, _compute_confidence) はそのまま実行
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# gmo_screener ディレクトリを import パスに追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import (
    BUY_THRESHOLD,
    SELL_THRESHOLD,
    _compute_confidence,
    _score_bollinger,
    _score_ma,
    _score_macd,
    _score_rsi,
    generate_signal,
)

# ============================================================
# _score_rsi
# ============================================================


class TestScoreRsi:
    def test_below_30_strong_buy(self):
        score, reason = _score_rsi(29.9)
        assert score == 100
        assert "売られすぎ" in reason

    def test_exactly_30_is_not_below_30(self):
        # rsi=30.0 は `< 30` が偽 → `< 40` の分岐 → 50
        score, reason = _score_rsi(30.0)
        assert score == 50

    def test_between_30_and_40(self):
        score, _ = _score_rsi(35.0)
        assert score == 50

    def test_exactly_40_falls_into_below_50(self):
        # rsi=40.0 は `< 40` が偽 → `< 50` の分岐 → 20
        score, _ = _score_rsi(40.0)
        assert score == 20

    def test_between_40_and_50(self):
        score, _ = _score_rsi(45.0)
        assert score == 20

    def test_exactly_50_falls_into_le_60(self):
        # rsi=50.0 は `< 50` が偽 → `<= 60` の分岐 → -20
        score, _ = _score_rsi(50.0)
        assert score == -20

    def test_between_50_and_60(self):
        score, _ = _score_rsi(55.0)
        assert score == -20

    def test_exactly_60(self):
        score, _ = _score_rsi(60.0)
        assert score == -20

    def test_between_60_and_70(self):
        # rsi=65.0 は `<= 60` が偽 → `<= 70` の分岐 → -50
        score, _ = _score_rsi(65.0)
        assert score == -50

    def test_exactly_70(self):
        score, _ = _score_rsi(70.0)
        assert score == -50

    def test_above_70_strong_sell(self):
        score, reason = _score_rsi(70.1)
        assert score == -100
        assert "買われすぎ" in reason

    def test_reason_contains_rsi_value(self):
        _, reason = _score_rsi(25.0)
        assert "25.0" in reason


# ============================================================
# _score_ma
# ============================================================


class TestScoreMa:
    def test_golden_cross_within_5_days(self):
        score, reason = _score_ma("golden", 3, 100.0, 90.0)
        assert score == 100
        assert "ゴールデンクロス" in reason

    def test_golden_cross_exactly_5_days(self):
        score, _ = _score_ma("golden", 5, 100.0, 90.0)
        assert score == 100

    def test_golden_cross_6_days_ago_falls_to_trend(self):
        # 5日を超えたら short_ma > long_ma の上昇トレンド判定 → 40
        score, _ = _score_ma("golden", 6, 100.0, 90.0)
        assert score == 40

    def test_dead_cross_within_5_days(self):
        score, reason = _score_ma("dead", 2, 90.0, 100.0)
        assert score == -100
        assert "デッドクロス" in reason

    def test_dead_cross_6_days_ago_falls_to_trend(self):
        # 5日を超えたら short_ma < long_ma の下降トレンド判定 → -40
        score, _ = _score_ma("dead", 6, 90.0, 100.0)
        assert score == -40

    def test_no_cross_uptrend(self):
        score, _ = _score_ma("none", -1, 100.0, 80.0)
        assert score == 40

    def test_no_cross_downtrend(self):
        score, _ = _score_ma("none", -1, 80.0, 100.0)
        assert score == -40

    def test_short_ma_equals_long_ma(self):
        score, _ = _score_ma("none", -1, 100.0, 100.0)
        assert score == 0


# ============================================================
# _score_macd
# ============================================================


class TestScoreMacd:
    def test_macd_above_signal_hist_increasing_strong_buy(self):
        score, reason = _score_macd(100.0, 80.0, 20.0, True)
        assert score == 100
        assert "強い買い" in reason

    def test_macd_above_signal_hist_decreasing_moderate_buy(self):
        score, reason = _score_macd(100.0, 80.0, 10.0, False)
        assert score == 50
        assert "買い優勢" in reason

    def test_macd_below_signal_hist_decreasing_strong_sell(self):
        score, reason = _score_macd(80.0, 100.0, -20.0, False)
        assert score == -100
        assert "強い売り" in reason

    def test_macd_below_signal_hist_increasing_moderate_sell(self):
        score, reason = _score_macd(80.0, 100.0, -5.0, True)
        assert score == -50
        assert "売り優勢" in reason

    def test_macd_equals_signal(self):
        score, _ = _score_macd(100.0, 100.0, 0.0, False)
        assert score == 0


# ============================================================
# _score_bollinger
# ============================================================


class TestScoreBollinger:
    """pct_b の境界値を全網羅"""

    def test_below_lower_band_strong_buy(self):
        score, reason = _score_bollinger(-0.01, 8_000_000, 9_000_000, 7_000_000)
        assert score == 100
        assert "強い買い" in reason

    def test_exactly_zero_falls_into_below_0_2(self):
        # pct_b=0.0 は `< 0.0` が偽 → `< 0.2` の分岐 → 60
        score, _ = _score_bollinger(0.0, 8_500_000, 9_000_000, 8_000_000)
        assert score == 60

    def test_between_0_and_0_2(self):
        score, _ = _score_bollinger(0.1, 8_500_000, 9_000_000, 8_000_000)
        assert score == 60

    def test_exactly_0_2_falls_into_below_0_4(self):
        score, _ = _score_bollinger(0.2, 8_500_000, 9_000_000, 8_000_000)
        assert score == 20

    def test_between_0_2_and_0_4(self):
        score, _ = _score_bollinger(0.3, 8_500_000, 9_000_000, 8_000_000)
        assert score == 20

    def test_exactly_0_4_falls_into_le_0_6(self):
        score, _ = _score_bollinger(0.4, 8_500_000, 9_000_000, 8_000_000)
        assert score == 0

    def test_exactly_0_6(self):
        score, _ = _score_bollinger(0.6, 8_500_000, 9_000_000, 8_000_000)
        assert score == 0

    def test_between_0_6_and_0_8(self):
        # pct_b=0.61 は `<= 0.6` が偽 → `<= 0.8` の分岐 → -20
        score, _ = _score_bollinger(0.61, 8_500_000, 9_000_000, 8_000_000)
        assert score == -20

    def test_exactly_0_8(self):
        score, _ = _score_bollinger(0.8, 8_500_000, 9_000_000, 8_000_000)
        assert score == -20

    def test_between_0_8_and_1_0(self):
        score, _ = _score_bollinger(0.9, 8_500_000, 9_000_000, 8_000_000)
        assert score == -60

    def test_exactly_1_0(self):
        score, _ = _score_bollinger(1.0, 8_500_000, 9_000_000, 8_000_000)
        assert score == -60

    def test_above_upper_band_strong_sell(self):
        score, reason = _score_bollinger(1.01, 9_100_000, 9_000_000, 8_000_000)
        assert score == -100
        assert "強い売り" in reason


# ============================================================
# _compute_confidence
# ============================================================


class TestComputeConfidence:
    def test_all_4_positive_buy_high(self):
        scores = {"RSI": 100, "MA": 40, "MACD": 50, "BB": 60}
        assert _compute_confidence(scores, "buy") == "HIGH"

    def test_3_positive_buy_high(self):
        scores = {"RSI": 100, "MA": 40, "MACD": -100, "BB": 60}
        assert _compute_confidence(scores, "buy") == "HIGH"

    def test_2_positive_buy_medium(self):
        scores = {"RSI": 100, "MA": -100, "MACD": -100, "BB": 60}
        assert _compute_confidence(scores, "buy") == "MEDIUM"

    def test_1_positive_buy_low(self):
        scores = {"RSI": 100, "MA": -100, "MACD": -100, "BB": -60}
        assert _compute_confidence(scores, "buy") == "LOW"

    def test_0_positive_buy_low(self):
        scores = {"RSI": -100, "MA": -100, "MACD": -100, "BB": -60}
        assert _compute_confidence(scores, "buy") == "LOW"

    def test_all_4_negative_sell_high(self):
        scores = {"RSI": -100, "MA": -100, "MACD": -100, "BB": -60}
        assert _compute_confidence(scores, "sell") == "HIGH"

    def test_3_negative_sell_high(self):
        scores = {"RSI": -100, "MA": 40, "MACD": -100, "BB": -60}
        assert _compute_confidence(scores, "sell") == "HIGH"

    def test_2_negative_sell_medium(self):
        scores = {"RSI": -100, "MA": 40, "MACD": 50, "BB": -60}
        assert _compute_confidence(scores, "sell") == "MEDIUM"

    def test_hold_direction_always_low(self):
        scores = {"RSI": -100, "MA": -100, "MACD": -100, "BB": -100}
        assert _compute_confidence(scores, "hold") == "LOW"

    def test_score_zero_not_counted_as_positive_for_buy(self):
        # score=0 は buy方向に貢献しない
        scores = {"RSI": 0, "MA": 0, "MACD": 0, "BB": 0}
        assert _compute_confidence(scores, "buy") == "LOW"


# ============================================================
# generate_signal （GmoApi をフルモック）
# ============================================================


def _make_mock_api(prices: list[float], last_price: float) -> MagicMock:
    """generate_signal が内部で使う API メソッドをモック化して返す。"""
    api = MagicMock()
    # fetch_closing_prices が prices を返すように klines を組み立てる
    klines = [
        {"openTime": str(1_700_000_000_000 + i * 86_400_000), "close": str(p)}
        for i, p in enumerate(prices)
    ]
    api.get_klines.return_value = klines
    api.get_ticker.return_value = {"last": str(last_price)}
    return api


# テスト用に十分な価格データを生成するヘルパー
def _flat_prices(n: int = 40, value: float = 10_000_000.0) -> list[float]:
    """n 本の一定価格リスト。"""
    return [value] * n


def _rising_prices(n: int = 40, start: float = 9_000_000.0, step: float = 50_000.0) -> list[float]:
    """右肩上がりの価格リスト（RSI高め・上昇トレンド）。"""
    return [start + i * step for i in range(n)]


def _falling_prices(
    n: int = 40, start: float = 11_000_000.0, step: float = 50_000.0
) -> list[float]:
    """右肩下がりの価格リスト（RSI低め・下降トレンド）。"""
    return [start - i * step for i in range(n)]


class TestGenerateSignal:
    """generate_signal の統合テスト。外部API通信なし。"""

    def test_returns_required_keys(self):
        """戻り値に必須キーが全て存在する。"""
        prices = _flat_prices(40)
        required_keys = [
            "date",
            "symbol",
            "current_price",
            "rsi",
            "short_ma",
            "long_ma",
            "ma_cross",
            "ma_days_since_cross",
            "macd_line",
            "macd_signal",
            "macd_histogram",
            "bb_upper",
            "bb_middle",
            "bb_lower",
            "bb_pct_b",
            "tech_score",
            "signal",
            "confidence",
            "indicator_scores",
            "reasons",
        ]
        with patch("main.fetch_closing_prices", return_value=prices):
            api = MagicMock()
            api.get_ticker.return_value = {"last": "10000000"}
            result = generate_signal(api)

        for key in required_keys:
            assert key in result, f"キー '{key}' が戻り値に存在しない"

    def test_signal_is_buy_when_score_above_threshold(self):
        """スコアが BUY_THRESHOLD 以上なら signal='BUY'。"""
        prices = _falling_prices(40)  # 下落 → RSI低・売られすぎ → BUYシグナル寄り
        with patch("main.fetch_closing_prices", return_value=prices):
            api = MagicMock()
            api.get_ticker.return_value = {"last": str(prices[-1])}
            result = generate_signal(api)

        if result["tech_score"] >= BUY_THRESHOLD:
            assert result["signal"] == "BUY"

    def test_signal_is_sell_when_score_below_threshold(self):
        """スコアが SELL_THRESHOLD 以下なら signal='SELL'。"""
        prices = _rising_prices(40)  # 上昇 → RSI高・買われすぎ → SELLシグナル寄り
        with patch("main.fetch_closing_prices", return_value=prices):
            api = MagicMock()
            api.get_ticker.return_value = {"last": str(prices[-1])}
            result = generate_signal(api)

        if result["tech_score"] <= SELL_THRESHOLD:
            assert result["signal"] == "SELL"

    def test_signal_is_hold_when_score_in_range(self):
        """スコアが閾値内なら signal='HOLD'。"""
        prices = _flat_prices(40)  # 一定価格 → スコアほぼ0 → HOLD
        with patch("main.fetch_closing_prices", return_value=prices):
            api = MagicMock()
            api.get_ticker.return_value = {"last": "10000000"}
            result = generate_signal(api)

        assert SELL_THRESHOLD < result["tech_score"] < BUY_THRESHOLD
        assert result["signal"] == "HOLD"

    def test_signal_consistency_with_score(self):
        """signal と tech_score が矛盾しない。"""
        prices = _flat_prices(40)
        with patch("main.fetch_closing_prices", return_value=prices):
            api = MagicMock()
            api.get_ticker.return_value = {"last": "10000000"}
            result = generate_signal(api)

        score = result["tech_score"]
        signal = result["signal"]
        if score >= BUY_THRESHOLD:
            assert signal == "BUY"
        elif score <= SELL_THRESHOLD:
            assert signal == "SELL"
        else:
            assert signal == "HOLD"

    def test_indicator_scores_has_4_keys(self):
        """indicator_scores に RSI/MA/MACD/BB の4キーが存在する。"""
        prices = _flat_prices(40)
        with patch("main.fetch_closing_prices", return_value=prices):
            api = MagicMock()
            api.get_ticker.return_value = {"last": "10000000"}
            result = generate_signal(api)

        assert set(result["indicator_scores"].keys()) == {"RSI", "MA", "MACD", "BB"}

    def test_tech_score_is_average_of_4_indicator_scores(self):
        """tech_score が 4指標スコアの平均と一致する。"""
        prices = _flat_prices(40)
        with patch("main.fetch_closing_prices", return_value=prices):
            api = MagicMock()
            api.get_ticker.return_value = {"last": "10000000"}
            result = generate_signal(api)

        scores = result["indicator_scores"]
        expected = sum(scores.values()) / 4.0
        assert abs(result["tech_score"] - expected) < 0.01

    def test_reasons_has_4_entries(self):
        """reasons リストに4つの判断根拠が含まれる。"""
        prices = _flat_prices(40)
        with patch("main.fetch_closing_prices", return_value=prices):
            api = MagicMock()
            api.get_ticker.return_value = {"last": "10000000"}
            result = generate_signal(api)

        assert len(result["reasons"]) == 4

    def test_ticker_last_missing_falls_back_to_last_price(self):
        """ticker に 'last' がない場合、prices[-1] をフォールバックにする。"""
        prices = _flat_prices(40, value=9_500_000.0)
        with patch("main.fetch_closing_prices", return_value=prices):
            api = MagicMock()
            api.get_ticker.return_value = {}  # 'last' なし
            result = generate_signal(api)

        assert result["current_price"] == 9_500_000.0

    def test_raises_value_error_when_data_insufficient(self):
        """価格データが MIN_PRICES(34) 未満なら ValueError。"""
        from main import MIN_PRICES

        prices = _flat_prices(MIN_PRICES - 1)
        with patch("main.fetch_closing_prices", return_value=prices):
            api = MagicMock()
            api.get_ticker.return_value = {"last": "10000000"}
            with pytest.raises(ValueError, match="データ不足"):
                generate_signal(api)

    def test_exactly_min_prices_does_not_raise(self):
        """価格データがちょうど MIN_PRICES(34) 本なら正常実行。"""
        from main import MIN_PRICES

        prices = _flat_prices(MIN_PRICES)
        with patch("main.fetch_closing_prices", return_value=prices):
            api = MagicMock()
            api.get_ticker.return_value = {"last": "10000000"}
            result = generate_signal(api)  # 例外が出なければ OK

        assert "signal" in result

    def test_current_price_reflects_ticker_last(self):
        """current_price が ticker の last 値と一致する。"""
        prices = _flat_prices(40)
        with patch("main.fetch_closing_prices", return_value=prices):
            api = MagicMock()
            api.get_ticker.return_value = {"last": "12345678"}
            result = generate_signal(api)

        assert result["current_price"] == 12_345_678.0
