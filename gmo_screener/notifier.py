"""Gmail 通知モジュール"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_email(
    subject: str, html_body: str, gmail_addr: str, gmail_pass: str, to_addr: str
) -> None:
    """Gmail経由でHTML形式のメールを送信。"""
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


# ------------------------------------------------------------------ スクリーナー通知
_CROSS_LABELS = {"golden": "ゴールデンクロス", "dead": "デッドクロス", "none": "なし"}
_SIGNAL_LABELS = {"BUY": "買いシグナル", "SELL": "売りシグナル"}
_CONF_LABELS = {"HIGH": "高", "MEDIUM": "中", "LOW": "低"}
_SCORE_NAMES = {"RSI": "RSI(14)", "MA": "移動平均(5/20)", "MACD": "MACD(12/26/9)", "BB": "BB(20)"}


def notify_screener_signal(result: dict, gmail_addr: str, gmail_pass: str, to_addr: str) -> None:
    """BUY/SELL シグナル時のメール通知。"""
    signal = result["signal"]
    label = _SIGNAL_LABELS.get(signal, signal)
    conf = _CONF_LABELS.get(result["confidence"], result["confidence"])
    cross = _CROSS_LABELS.get(result["ma_cross"], result["ma_cross"])
    score_rows = [
        (name, f"{result['indicator_scores'][key]:+.0f}")
        for key, name in _SCORE_NAMES.items()
        if key in result["indicator_scores"]
    ]
    reason_html = "".join(f"<li>{r}</li>" for r in result["reasons"])

    subject = f"[Screener] BTC {label} (スコア:{result['tech_score']:+.0f} / {conf})"
    html = (
        f"<html><body>"
        f"<h2>BTC {label}</h2>"
        f"<table style='border-collapse:collapse'>"
        f"<tr><td style='padding:4px 12px;font-weight:bold'>日付</td><td style='padding:4px 12px'>{result['date']}</td></tr>"
        f"<tr><td style='padding:4px 12px;font-weight:bold'>現在価格</td><td style='padding:4px 12px'>¥{result['current_price']:,.0f}</td></tr>"
        f"<tr><td style='padding:4px 12px;font-weight:bold'>シグナル</td><td style='padding:4px 12px'>{label}</td></tr>"
        f"<tr><td style='padding:4px 12px;font-weight:bold'>信頼度</td><td style='padding:4px 12px'>{conf}</td></tr>"
        f"<tr><td style='padding:4px 12px;font-weight:bold'>総合スコア</td><td style='padding:4px 12px'>{result['tech_score']:+.1f}</td></tr>"
        f"</table>"
        f"<h3>指標詳細</h3>"
        f"<table style='border-collapse:collapse'>"
        f"<tr><td style='padding:4px 12px;font-weight:bold'>RSI(14)</td><td style='padding:4px 12px'>{result['rsi']:.1f}</td></tr>"
        f"<tr><td style='padding:4px 12px;font-weight:bold'>短期MA(5)</td><td style='padding:4px 12px'>¥{result['short_ma']:,.0f}</td></tr>"
        f"<tr><td style='padding:4px 12px;font-weight:bold'>長期MA(20)</td><td style='padding:4px 12px'>¥{result['long_ma']:,.0f}</td></tr>"
        f"<tr><td style='padding:4px 12px;font-weight:bold'>MAクロス</td><td style='padding:4px 12px'>{cross}</td></tr>"
        f"<tr><td style='padding:4px 12px;font-weight:bold'>MACD</td><td style='padding:4px 12px'>{result['macd_line']:+,.0f}</td></tr>"
        f"<tr><td style='padding:4px 12px;font-weight:bold'>MACDシグナル</td><td style='padding:4px 12px'>{result['macd_signal']:+,.0f}</td></tr>"
        f"<tr><td style='padding:4px 12px;font-weight:bold'>BB上限</td><td style='padding:4px 12px'>¥{result['bb_upper']:,.0f}</td></tr>"
        f"<tr><td style='padding:4px 12px;font-weight:bold'>BB下限</td><td style='padding:4px 12px'>¥{result['bb_lower']:,.0f}</td></tr>"
        f"<tr><td style='padding:4px 12px;font-weight:bold'>%B</td><td style='padding:4px 12px'>{result['bb_pct_b']:.2f}</td></tr>"
        f"</table>"
        f"<h3>スコア内訳</h3>"
        f"<table style='border-collapse:collapse'>"
        + "".join(
            f"<tr><td style='padding:4px 12px;font-weight:bold'>{name}</td>"
            f"<td style='padding:4px 12px'>{score}</td></tr>"
            for name, score in score_rows
        )
        + f"</table>"
        f"<h3>判断根拠</h3><ul>{reason_html}</ul>"
        f"</body></html>"
    )
    send_email(subject, html, gmail_addr, gmail_pass, to_addr)
