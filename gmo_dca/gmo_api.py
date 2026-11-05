"""GMO Coin API クライアント（公開・非公開）"""

import hashlib
import hmac
import json
import time
from datetime import datetime

import requests


class GmoApiError(Exception):
    """GMO API 呼び出しエラー"""


class GmoApi:
    PUBLIC_BASE = "https://api.coin.z.com/public"
    PRIVATE_BASE = "https://api.coin.z.com/private"

    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret

    # ------------------------------------------------------------------ auth
    def _make_timestamp(self) -> str:
        # ドキュメント公式サンプルに準拠: 秒単位UNIXタイムスタンプ + "000"
        return f"{int(time.mktime(datetime.now().timetuple()))}000"

    def _sign(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        text = timestamp + method + path + body
        return hmac.new(
            bytes(self.api_secret.encode("ascii")), bytes(text.encode("ascii")), hashlib.sha256
        ).hexdigest()

    def _auth_headers(self, method: str, path: str, body: str = "") -> dict:
        timestamp = self._make_timestamp()
        sign = self._sign(timestamp, method, path, body)
        return {
            "API-KEY": self.api_key,
            "API-TIMESTAMP": timestamp,
            "API-SIGN": sign,
        }

    # ------------------------------------------------------------------ HTTP
    def _public_get(self, path: str) -> dict:
        resp = requests.get(self.PUBLIC_BASE + path, timeout=30)
        body = resp.json()
        if body.get("status") != 0:
            raise GmoApiError(f"API error: {body}")
        return body

    def _private_get(self, path: str) -> dict:
        # GMO仕様: GETの署名にはクエリ文字列を含めない
        sign_path = path.split("?")[0]
        headers = self._auth_headers("GET", sign_path)
        resp = requests.get(self.PRIVATE_BASE + path, headers=headers, timeout=30)
        body = resp.json()
        if body.get("status") != 0:
            raise GmoApiError(f"API error: {body}")
        return body

    def _private_post(self, path: str, body: dict) -> dict:
        body_str = json.dumps(body)
        headers = self._auth_headers("POST", path, body_str)
        resp = requests.post(
            self.PRIVATE_BASE + path,
            headers=headers,
            data=body_str,
            timeout=30,
        )
        result = resp.json()
        if result.get("status") != 0:
            raise GmoApiError(f"API error: {result}")
        return result

    # ----------------------------------------------------------- 公開API
    def get_klines(self, symbol: str, date_str: str) -> list[dict]:
        """日足K-lineを取得。date_str は YYYYMMDD 形式。"""
        path = f"/v1/klines?symbol={symbol}&interval=1day&date={date_str}"
        resp = self._public_get(path)
        return resp.get("data", [])

    def get_ticker(self, symbol: str) -> dict:
        """Ticker（最終価格等）を取得。symbol は BTC_JPY 等。"""
        path = f"/v1/ticker?symbol={symbol}"
        resp = self._public_get(path)
        data = resp.get("data", [])
        if not data:
            raise GmoApiError(f"Ticker data empty for {symbol}")
        return data[0]

    # ----------------------------------------------------------- 非公開API
    def get_executions(self, symbol: str, page: int = 1, count: int = 100) -> list[dict]:
        """最新の約定履歴を取得。symbol は BTC_JPY 等。"""
        path = f"/v1/latestExecutions?symbol={symbol}&count={count}"
        resp = self._private_get(path)
        return (resp.get("data") or {}).get("list", [])

    def get_available_amount(self) -> float:
        """利用可能な日本円残高を返す。"""
        path = "/v1/account/assets"
        resp = self._private_get(path)
        for asset in resp.get("data", []):
            if asset.get("symbol") == "JPY":
                return float(asset.get("available", 0))
        return 0.0

    def place_market_buy(self, symbol: str, size: str) -> dict:
        """現物・成行買い注文を発注。size は文字列（例: "0.0003"）。"""
        path = "/v1/order"
        body = {
            "symbol": symbol,
            "side": "BUY",
            "executionType": "MARKET",
            "size": size,
        }
        return self._private_post(path, body)

    # ----------------------------------------------------------- ヘルパー
    def has_bought_since(self, symbol: str, since: datetime) -> bool:
        """since 以降に symbol の買い約定があるか判定。

        約定履歴APIがエラーの場合は例外をそのまま伝播させる
        （呼び出し元で安全策として処理を中断させるため）。
        """
        page = 1
        while True:
            executions = self.get_executions(symbol, page=page, count=100)
            if not executions:
                return False
            for ex in executions:
                ts_str = ex.get("timestamp", "")
                # GMO の timestamp 形式: "2024-01-16T12:34:56.789Z"
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    continue
                if ts >= since and ex.get("side") == "BUY":
                    return True
                # 約定履歴は新しい順 — since より古いデータに到達したら終了
                if ts < since:
                    return False
            page += 1
            if page > 10:  # 安全上限
                return False
