"""balances/gmo_client.py のユニットテスト。

requests は一切呼ばない（_public_get / _private_get を patch して外部通信を遮断）。
"""

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from balances.gmo_client import GmoApi, GmoApiError


def _api() -> GmoApi:
    return GmoApi("key", "secret")


class TestGetAvailableAmount:
    def test_returns_jpy_available(self):
        api = _api()
        with patch.object(
            api,
            "_private_get",
            return_value={
                "status": 0,
                "data": [
                    {"symbol": "JPY", "amount": "100000", "available": "80000"},
                    {"symbol": "BTC", "amount": "0.5", "available": "0.5"},
                ],
            },
        ):
            assert api.get_available_amount() == 80000.0

    def test_no_jpy_record_returns_zero(self):
        api = _api()
        with patch.object(
            api,
            "_private_get",
            return_value={
                "status": 0,
                "data": [
                    {"symbol": "BTC", "amount": "0.5", "available": "0.5"},
                ],
            },
        ):
            assert api.get_available_amount() == 0.0

    def test_empty_data_returns_zero(self):
        api = _api()
        with patch.object(api, "_private_get", return_value={"status": 0, "data": []}):
            assert api.get_available_amount() == 0.0


class TestGetAllAssets:
    def test_returns_data_list(self):
        api = _api()
        data = [{"symbol": "JPY", "amount": "1000"}, {"symbol": "BTC", "amount": "0.1"}]
        with patch.object(api, "_private_get", return_value={"status": 0, "data": data}):
            assert api.get_all_assets() == data

    def test_missing_data_key_returns_empty_list(self):
        api = _api()
        with patch.object(api, "_private_get", return_value={"status": 0}):
            assert api.get_all_assets() == []


class TestGetCryptoValuationJpy:
    def test_single_symbol_valuation(self):
        api = _api()
        with (
            patch.object(
                api,
                "get_all_assets",
                return_value=[
                    {"symbol": "JPY", "amount": "1000"},
                    {"symbol": "BTC", "amount": "0.01"},
                ],
            ),
            patch.object(api, "get_ticker", return_value={"last": "10000000"}),
        ):
            assert api.get_crypto_valuation_jpy(["BTC"]) == 100000.0

    def test_multiple_symbols_summed(self):
        api = _api()
        with (
            patch.object(
                api,
                "get_all_assets",
                return_value=[
                    {"symbol": "BTC", "amount": "0.01"},
                    {"symbol": "ETH", "amount": "1.0"},
                ],
            ),
            patch.object(
                api,
                "get_ticker",
                side_effect=[
                    {"last": "10000000"},  # BTC
                    {"last": "300000"},  # ETH
                ],
            ),
        ):
            assert api.get_crypto_valuation_jpy(["BTC", "ETH"]) == 100000.0 + 300000.0

    def test_zero_holding_symbol_skipped_no_ticker_call(self):
        api = _api()
        with (
            patch.object(
                api,
                "get_all_assets",
                return_value=[
                    {"symbol": "BTC", "amount": "0"},
                ],
            ),
            patch.object(api, "get_ticker") as mock_ticker,
        ):
            total = api.get_crypto_valuation_jpy(["BTC"])
        mock_ticker.assert_not_called()
        assert total == 0.0

    def test_ticker_error_for_one_symbol_ignored(self):
        """1銘柄のTicker取得失敗で全体が失敗しない。"""
        api = _api()
        with (
            patch.object(
                api,
                "get_all_assets",
                return_value=[
                    {"symbol": "BTC", "amount": "0.01"},
                    {"symbol": "ETH", "amount": "1.0"},
                ],
            ),
            patch.object(
                api,
                "get_ticker",
                side_effect=[
                    GmoApiError("ticker down"),
                    {"last": "300000"},
                ],
            ),
        ):
            total = api.get_crypto_valuation_jpy(["BTC", "ETH"])
        assert total == 300000.0

    def test_no_holdings_returns_zero(self):
        api = _api()
        with patch.object(
            api, "get_all_assets", return_value=[{"symbol": "JPY", "amount": "1000"}]
        ):
            assert api.get_crypto_valuation_jpy(["BTC", "ETH"]) == 0.0


class TestPrivateGetErrorPropagation:
    def test_api_error_status_raises(self):
        api = _api()
        with patch("balances.gmo_client.requests.get") as mock_get:
            mock_get.return_value.json.return_value = {"status": 5, "messages": ["error"]}
            try:
                api._private_get("/v1/account/assets")
                assert False, "GmoApiError が発生するはず"
            except GmoApiError:
                pass
