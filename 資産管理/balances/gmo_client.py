"""GMO Coin API クライアント（資産管理用）。

gmo_dca/gmo_api.py の GmoApi クラスをコピーしたもの（gmo_dca と gmo_screener が
同一実装をコピーして持っている既存の慣習を踏襲）。仕様変更時は3プロジェクト間で
同期が必要な点に注意。

資産管理では発注系メソッド（place_market_buy）は一切呼び出さない。
GMO API キーは可能であれば「残高照会専用」の新規発行キーを使うことを推奨する
（gmo_dca の発注権限つきキーをそのまま流用するとリスクがある）。

gmo_dca 版に対する追加:
  - get_all_assets(): /v1/account/assets の全件（JPY以外の暗号資産も含む）を返す
  - get_crypto_valuation_jpy(): 保有中の暗号資産を時価（get_ticker）で円換算し合計する
"""

import hashlib
import hmac
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

    # ----------------------------------------------------------- 公開API
    def get_ticker(self, symbol: str) -> dict:
        """Ticker（最終価格等）を取得。symbol は BTC_JPY 等。"""
        path = f"/v1/ticker?symbol={symbol}"
        resp = self._public_get(path)
        data = resp.get("data", [])
        if not data:
            raise GmoApiError(f"Ticker data empty for {symbol}")
        return data[0]

    # ----------------------------------------------------------- 非公開API
    def get_available_amount(self) -> float:
        """利用可能な日本円現金残高を返す。"""
        for asset in self.get_all_assets():
            if asset.get("symbol") == "JPY":
                return float(asset.get("available", 0))
        return 0.0

    def get_all_assets(self) -> list[dict]:
        """/v1/account/assets の生データ全件（JPY現金 + 保有暗号資産）を返す。"""
        resp = self._private_get("/v1/account/assets")
        return resp.get("data", [])

    def get_crypto_valuation_jpy(self, symbols: list[str] = ("BTC", "ETH")) -> float:
        """保有中の暗号資産（symbols指定分）を現在時価で円換算し合計を返す。

        Ticker取得に失敗した銘柄はログを呼び出し元に委ね、価値0として無視する
        （1銘柄のTicker障害で全体の残高取得が失敗しないようにするため）。
        """
        total = 0.0
        assets = self.get_all_assets()
        holdings = {a.get("symbol"): float(a.get("amount", 0)) for a in assets}

        for symbol in symbols:
            qty = holdings.get(symbol, 0.0)
            if qty <= 0:
                continue
            try:
                ticker = self.get_ticker(f"{symbol}_JPY")
                price = float(ticker.get("last", 0))
            except GmoApiError:
                continue
            total += qty * price
        return total
