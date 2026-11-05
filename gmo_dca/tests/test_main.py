"""
main.py のユニットテスト

外部通信なし:
  - GmoApi は MagicMock(spec=GmoApi) で完全差し替え
  - notifier.notify_* は patch で副作用を排除
  - datetime.now は monkeypatch で固定
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gmo_api import GmoApi, GmoApiError

import main as main_module
from main import BUDGET_BOOST, BUDGET_NORMAL, floor_quantity, get_month_16th, process_coin

JST = timezone(timedelta(hours=9))

# ============================================================
# floor_quantity
# ============================================================


class TestFloorQuantity:
    def test_btc_4_decimals(self):
        # ¥5000 / ¥10,000,000 = 0.0005 → そのまま
        assert floor_quantity(0.0005, 4) == 0.0005

    def test_truncates_not_rounds(self):
        # 0.12345 を4桁切り捨て → 0.1234（0.1235 に切り上げしない）
        assert floor_quantity(0.12345, 4) == 0.1234

    def test_eth_2_decimals(self):
        assert floor_quantity(0.159, 2) == 0.15

    def test_zero_decimals(self):
        assert floor_quantity(3.9, 0) == 3.0

    def test_exact_value_unchanged(self):
        assert floor_quantity(0.1234, 4) == 0.1234

    def test_budget_div_high_price(self):
        # ¥5000 / ¥9,999,999 ≒ 0.00050000... → 4桁切り捨て = 0.0005
        qty = floor_quantity(5000 / 9_999_999, 4)
        assert qty == 0.0005

    def test_budget_div_very_high_price_gives_zero(self):
        # ¥5000 / ¥999,999,999 ≒ 0.000005 → 4桁切り捨て = 0.0000
        qty = floor_quantity(5000 / 999_999_999, 4)
        assert qty == 0.0


# ============================================================
# get_month_16th
# ============================================================


class TestGetMonth16th:
    def test_returns_16th_of_same_month(self):
        now = datetime(2025, 3, 25, 10, 0, 0, tzinfo=JST)
        result = get_month_16th(now)
        assert result.day == 16
        assert result.month == 3
        assert result.year == 2025

    def test_time_is_midnight(self):
        now = datetime(2025, 3, 25, 15, 30, 0, tzinfo=JST)
        result = get_month_16th(now)
        assert result.hour == 0
        assert result.minute == 0
        assert result.second == 0

    def test_timezone_is_jst(self):
        now = datetime(2025, 3, 25, tzinfo=JST)
        result = get_month_16th(now)
        assert result.tzinfo == JST

    def test_works_on_the_16th(self):
        now = datetime(2025, 3, 16, 0, 0, 0, tzinfo=JST)
        result = get_month_16th(now)
        assert result.day == 16


# ============================================================
# process_coin ヘルパー
# ============================================================

DUMMY = dict(gmail_addr="a@example.com", gmail_pass="pass", to_addr="b@example.com")
SINCE = datetime(2025, 4, 16, tzinfo=JST)


def _make_api(**kwargs) -> MagicMock:
    """GmoApi モック。デフォルトは「未購入・RSI50・残高10万・価格1000万・注文成功」。"""
    api = MagicMock(spec=GmoApi)
    api.has_bought_since.return_value = kwargs.get("has_bought_since", False)
    api.get_available_amount.return_value = kwargs.get("available", 100_000.0)
    api.get_ticker.return_value = {"last": str(kwargs.get("price", 10_000_000))}
    api.place_market_buy.return_value = {"orderId": "123"}
    return api


def _run(api, rsi=50.0):
    """process_coin を呼ぶショートカット。
    - rsi は patch で注入
    - SMTP だけ遮断（実メール送信を防ぐ）
    - notify_* の観測は各テスト側で行う
    """
    with patch("main.get_rsi", return_value=rsi), patch("notifier.smtplib.SMTP"):
        process_coin(
            api,
            "BTC",
            4,
            0.0001,
            SINCE,
            DUMMY["gmail_addr"],
            DUMMY["gmail_pass"],
            DUMMY["to_addr"],
        )


# ============================================================
# process_coin — 二重購入ガード
# ============================================================


class TestProcessCoinAlreadyPurchased:
    def test_skip_when_already_bought(self):
        api = _make_api(has_bought_since=True)
        with patch("main.notify_already_purchased") as mock_notify:
            _run(api)
        mock_notify.assert_called_once()

    def test_no_order_when_already_bought(self):
        api = _make_api(has_bought_since=True)
        with patch("main.notify_already_purchased"):
            _run(api)
        api.place_market_buy.assert_not_called()

    def test_no_rsi_check_when_already_bought(self):
        api = _make_api(has_bought_since=True)
        with patch("main.notify_already_purchased"), patch("main.get_rsi") as mock_rsi:
            process_coin(api, "BTC", 4, 0.0001, SINCE, **DUMMY)
        mock_rsi.assert_not_called()

    def test_api_error_on_history_check_propagates(self):
        """約定履歴APIエラーは例外をそのまま伝播させる（呼び出し元で中断）。"""
        api = _make_api()
        api.has_bought_since.side_effect = GmoApiError("API down")
        with pytest.raises(GmoApiError):
            _run(api)


# ============================================================
# process_coin — RSI 判定
# ============================================================


class TestProcessCoinRsi:
    def test_rsi_above_70_skips(self):
        api = _make_api()
        with patch("main.notify_rsi_skip") as mock_skip:
            _run(api, rsi=70.0)
        mock_skip.assert_called_once()
        api.place_market_buy.assert_not_called()

    def test_rsi_exactly_70_skips(self):
        api = _make_api()
        with patch("main.notify_rsi_skip") as mock_skip:
            _run(api, rsi=70.0)
        mock_skip.assert_called_once()

    def test_rsi_just_below_70_does_not_skip(self):
        api = _make_api()
        with patch("main.notify_rsi_skip") as mock_skip:
            _run(api, rsi=69.9)
        mock_skip.assert_not_called()

    def test_rsi_below_30_uses_boost_budget(self):
        """RSI < 30 → BUDGET_BOOST(¥7500) で数量計算。"""
        api = _make_api(price=10_000_000)
        with patch("main.notify_purchase") as mock_notify:
            _run(api, rsi=29.9)
        # ¥7500 / ¥10,000,000 = 0.00075 → 4桁切り捨て = 0.0007
        args = mock_notify.call_args
        assert args[0][3] == BUDGET_BOOST  # budget 引数

    def test_rsi_exactly_30_uses_normal_budget(self):
        """RSI=30.0 は boost 対象外（< 30 が偽）→ BUDGET_NORMAL(¥5000)。"""
        api = _make_api(price=10_000_000)
        with patch("main.notify_purchase") as mock_notify:
            _run(api, rsi=30.0)
        args = mock_notify.call_args
        assert args[0][3] == BUDGET_NORMAL

    def test_rsi_normal_range_uses_normal_budget(self):
        api = _make_api(price=10_000_000)
        with patch("main.notify_purchase") as mock_notify:
            _run(api, rsi=50.0)
        args = mock_notify.call_args
        assert args[0][3] == BUDGET_NORMAL

    def test_rsi_api_error_notifies_and_returns(self):
        api = _make_api()
        with (
            patch("main.get_rsi", side_effect=GmoApiError("fail")),
            patch("main.notify_error") as mock_err,
        ):
            process_coin(api, "BTC", 4, 0.0001, SINCE, **DUMMY)
        mock_err.assert_called_once()
        api.place_market_buy.assert_not_called()

    def test_rsi_value_error_notifies_and_returns(self):
        api = _make_api()
        with (
            patch("main.get_rsi", side_effect=ValueError("short")),
            patch("main.notify_error") as mock_err,
        ):
            process_coin(api, "BTC", 4, 0.0001, SINCE, **DUMMY)
        mock_err.assert_called_once()
        api.place_market_buy.assert_not_called()


# ============================================================
# process_coin — 残高チェック
# ============================================================


class TestProcessCoinBalance:
    def test_insufficient_balance_notifies(self):
        api = _make_api(available=4_999.0)  # BUDGET_NORMAL=5000 に足りない
        with patch("main.notify_balance_insufficient") as mock_notify:
            _run(api, rsi=50.0)
        mock_notify.assert_called_once()
        api.place_market_buy.assert_not_called()

    def test_sufficient_balance_proceeds(self):
        api = _make_api(available=5_000.0)
        with patch("main.notify_purchase"):
            _run(api, rsi=50.0)
        api.place_market_buy.assert_called_once()

    def test_balance_api_error_notifies_and_returns(self):
        api = _make_api()
        api.get_available_amount.side_effect = GmoApiError("fail")
        with patch("main.notify_error") as mock_err:
            _run(api, rsi=50.0)
        mock_err.assert_called_once()
        api.place_market_buy.assert_not_called()


# ============================================================
# process_coin — 価格・数量チェック
# ============================================================


class TestProcessCoinPriceQty:
    def test_zero_price_notifies_error(self):
        api = _make_api(price=0)
        with patch("main.notify_error") as mock_err:
            _run(api, rsi=50.0)
        mock_err.assert_called_once()
        api.place_market_buy.assert_not_called()

    def test_ticker_api_error_notifies_and_returns(self):
        api = _make_api()
        api.get_ticker.side_effect = GmoApiError("fail")
        with patch("main.notify_error") as mock_err:
            _run(api, rsi=50.0)
        mock_err.assert_called_once()
        api.place_market_buy.assert_not_called()

    def test_qty_below_min_notifies_balance_insufficient(self):
        """価格が高すぎて数量が最小単位(0.0001)を下回る場合。"""
        api = _make_api(price=999_999_999)  # ¥5000 / ~10億 → qty ≒ 0
        with patch("main.notify_balance_insufficient") as mock_notify:
            _run(api, rsi=50.0)
        mock_notify.assert_called_once()
        api.place_market_buy.assert_not_called()

    def test_qty_exactly_at_min_proceeds(self):
        """¥5000 / ¥50,000,000 = 0.0001 → ちょうど最小単位で注文できる。"""
        api = _make_api(price=50_000_000)
        with patch("main.notify_purchase"):
            _run(api, rsi=50.0)
        api.place_market_buy.assert_called_once()


# ============================================================
# process_coin — 注文
# ============================================================


class TestProcessCoinOrder:
    def test_successful_order_calls_place_market_buy(self):
        api = _make_api(price=10_000_000)
        with patch("main.notify_purchase"):
            _run(api, rsi=50.0)
        api.place_market_buy.assert_called_once_with("BTC", "0.0005")

    def test_successful_order_notifies_purchase(self):
        api = _make_api(price=10_000_000)
        with patch("main.notify_purchase") as mock_notify:
            _run(api, rsi=50.0)
        mock_notify.assert_called_once()
        args = mock_notify.call_args[0]
        assert args[0] == "BTC"  # symbol
        assert args[1] == "0.0005"  # size
        assert args[2] == 10_000_000.0  # price
        assert args[3] == BUDGET_NORMAL  # budget

    def test_order_api_error_notifies_error(self):
        api = _make_api()
        api.place_market_buy.side_effect = GmoApiError("order failed")
        with patch("main.notify_error") as mock_err:
            _run(api, rsi=50.0)
        mock_err.assert_called_once()

    def test_order_size_uses_floor_not_round(self):
        """切り捨て確認: ¥5000 / ¥7,777,777 ≒ 0.000642... → 0.0006"""
        api = _make_api(price=7_777_777)
        with patch("main.notify_purchase"):
            _run(api, rsi=50.0)
        api.place_market_buy.assert_called_once_with("BTC", "0.0006")


# ============================================================
# main() — 日付チェック・全体フロー
# ============================================================


class TestMain:
    BASE_ENV = {
        "GMO_API_KEY": "key",
        "GMO_API_SECRET": "secret",
        "GMAIL_ADDRESS": "a@example.com",
        "GMAIL_APP_PASSWORD": "pass",
        "NOTIFY_TO_ADDRESS": "b@example.com",
    }

    def _run_main(self, day: int, process_coin_mock=None):
        fixed_now = datetime(2025, 4, day, 10, 0, 0, tzinfo=JST)
        with (
            patch.dict(os.environ, self.BASE_ENV),
            patch("main.datetime") as mock_dt,
            patch("main.GmoApi"),
            patch("main.process_coin", process_coin_mock or MagicMock()),
        ):
            mock_dt.now.return_value = fixed_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            main_module.main()

    def test_before_16th_exits_early(self):
        mock_process = MagicMock()
        self._run_main(day=15, process_coin_mock=mock_process)
        mock_process.assert_not_called()

    def test_on_16th_runs_process_coin(self):
        mock_process = MagicMock()
        self._run_main(day=16, process_coin_mock=mock_process)
        assert mock_process.call_count == 2  # BTC + ETH

    def test_after_16th_runs_process_coin(self):
        mock_process = MagicMock()
        self._run_main(day=30, process_coin_mock=mock_process)
        assert mock_process.call_count == 2

    def test_missing_env_var_exits(self):
        with (
            patch.dict(os.environ, {"GMO_API_KEY": ""}, clear=False),
            pytest.raises(SystemExit) as exc,
        ):
            main_module.main()
        assert exc.value.code == 1

    def test_gmo_api_error_in_process_coin_exits(self):
        def raise_gmo(*args, **kwargs):
            raise GmoApiError("API down")

        with (
            patch.dict(os.environ, self.BASE_ENV),
            patch("main.datetime") as mock_dt,
            patch("main.GmoApi"),
            patch("main.process_coin", side_effect=raise_gmo),
            patch("main.notify_error"),
            pytest.raises(SystemExit) as exc,
        ):
            mock_dt.now.return_value = datetime(2025, 4, 16, 10, 0, 0, tzinfo=JST)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            main_module.main()
        assert exc.value.code == 1

    def test_unexpected_error_in_process_coin_exits(self):
        def raise_unexpected(*args, **kwargs):
            raise RuntimeError("unexpected")

        with (
            patch.dict(os.environ, self.BASE_ENV),
            patch("main.datetime") as mock_dt,
            patch("main.GmoApi"),
            patch("main.process_coin", side_effect=raise_unexpected),
            patch("main.notify_error"),
            pytest.raises(SystemExit) as exc,
        ):
            mock_dt.now.return_value = datetime(2025, 4, 16, 10, 0, 0, tzinfo=JST)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            main_module.main()
        assert exc.value.code == 1
