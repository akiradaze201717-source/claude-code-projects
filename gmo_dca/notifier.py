"""Gmail 通知モジュール"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

NOTIFY_ENABLED = True  # True に戻すと通知再開


def send_email(
    subject: str, html_body: str, gmail_addr: str, gmail_pass: str, to_addr: str
) -> None:
    """Gmail経由でHTML形式のメールを送信。"""
    if not NOTIFY_ENABLED:
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_addr
    msg["To"] = to_addr
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(gmail_addr, gmail_pass)
        server.sendmail(gmail_addr, to_addr, msg.as_string())


def _make_html(title: str, rows: list[tuple[str, str]]) -> str:
    """シンプルなHTMLメール本文を生成。"""
    row_html = "".join(
        f"<tr><td style='padding:4px 12px;font-weight:bold'>{k}</td>"
        f"<td style='padding:4px 12px'>{v}</td></tr>"
        for k, v in rows
    )
    return (
        f"<html><body>"
        f"<h2>{title}</h2>"
        f"<table style='border-collapse:collapse'>{row_html}</table>"
        f"</body></html>"
    )


def notify_purchase(
    symbol: str,
    size: str,
    price: float,
    budget: int,
    rsi: float,
    gmail_addr: str,
    gmail_pass: str,
    to_addr: str,
) -> None:
    subject = f"[DCA] {symbol} 購入完了"
    html = _make_html(
        "購入完了",
        [
            ("銘柄", symbol),
            ("数量", size),
            ("参考価格", f"¥{price:,.0f}"),
            ("予算", f"¥{budget:,}"),
            ("RSI(14)", f"{rsi:.1f}"),
        ],
    )
    send_email(subject, html, gmail_addr, gmail_pass, to_addr)


def notify_rsi_skip(
    symbol: str, rsi: float, gmail_addr: str, gmail_pass: str, to_addr: str
) -> None:
    subject = f"[DCA] {symbol} RSIスキップ (RSI={rsi:.1f})"
    html = _make_html(
        "RSI過熱 — 購入保留",
        [
            ("銘柄", symbol),
            ("RSI(14)", f"{rsi:.1f}"),
            ("判定", "RSI ≥ 70 のため翌日に持ち越し"),
        ],
    )
    send_email(subject, html, gmail_addr, gmail_pass, to_addr)


def notify_already_purchased(symbol: str, gmail_addr: str, gmail_pass: str, to_addr: str) -> None:
    subject = f"[DCA] {symbol} 当月購入済み"
    html = _make_html(
        "当月分は購入済み",
        [
            ("銘柄", symbol),
            ("状態", "今月16日以降に購入履歴あり — スキップ"),
        ],
    )
    send_email(subject, html, gmail_addr, gmail_pass, to_addr)


def notify_balance_insufficient(
    symbol: str, required: int, available: float, gmail_addr: str, gmail_pass: str, to_addr: str
) -> None:
    subject = f"[DCA] {symbol} 残高不足"
    html = _make_html(
        "残高不足 — 購入スキップ",
        [
            ("銘柄", symbol),
            ("必要額", f"¥{required:,}"),
            ("利用可能残高", f"¥{available:,.0f}"),
        ],
    )
    send_email(subject, html, gmail_addr, gmail_pass, to_addr)


def notify_error(error_message: str, gmail_addr: str, gmail_pass: str, to_addr: str) -> None:
    subject = "[DCA] エラー発生"
    html = _make_html(
        "エラー",
        [
            ("詳細", error_message),
        ],
    )
    send_email(subject, html, gmail_addr, gmail_pass, to_addr)
