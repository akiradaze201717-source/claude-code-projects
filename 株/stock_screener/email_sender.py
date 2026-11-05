"""Gmail SMTP送信モジュール（HTML形式）"""

import logging
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from 株.stock_screener.screener import ScreeningResult, format_oku

logger = logging.getLogger(__name__)

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587


def send_screening_email(
    results: list[ScreeningResult],
    gmail_address: str,
    gmail_app_password: str,
    recipient: str,
    stats: dict | None = None,
) -> None:
    """スクリーニング結果をHTMLメールで送信する。"""
    today = date.today().strftime("%Y-%m-%d")
    primary_count = sum(1 for r in results if r.is_primary)
    subject = (
        f"[清原式スクリーニング] {today} "
        f"本命{primary_count}件 / 準候補{len(results) - primary_count}件"
    )

    html = _build_html(results, today, stats)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_address
    msg["To"] = recipient
    msg.attach(MIMEText(html, "html", "utf-8"))

    logger.info("メール送信中: %s → %s", gmail_address, recipient)
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(gmail_address, gmail_app_password)
        server.send_message(msg)

    logger.info("メール送信完了: %s", subject)


def _build_html(
    results: list[ScreeningResult],
    today: str,
    stats: dict | None,
) -> str:
    if results:
        rows = ""
        for r in results:
            yahoo_url = f"https://finance.yahoo.co.jp/quote/{r.code.replace('.T', '')}"
            badges = ""
            if r.is_primary:
                badges += (
                    '<span style="background:#e74c3c;color:#fff;padding:1px 5px;'
                    'border-radius:3px;font-size:11px;margin-right:3px;">本命</span>'
                )
            else:
                badges += (
                    '<span style="background:#95a5a6;color:#fff;padding:1px 5px;'
                    'border-radius:3px;font-size:11px;margin-right:3px;">準</span>'
                )
            if r.is_small_cap:
                badges += (
                    '<span style="background:#9b59b6;color:#fff;padding:1px 5px;'
                    'border-radius:3px;font-size:11px;">小型</span>'
                )
            # 投資有価証券データが欠損している銘柄は比率が過小評価の可能性 → 印
            inv_note = (
                ""
                if r.has_inv_data
                else '<span style="color:#e67e22;" title="投資有価証券データ欠損">*</span>'
            )
            nc_color = (
                "#e74c3c" if r.is_primary else "#27ae60" if r.net_cash_ratio >= 0.85 else "#333"
            )
            rows += f"""
            <tr>
                <td style="padding:7px 10px;border-bottom:1px solid #eee;white-space:nowrap;">
                    <a href="{yahoo_url}" style="color:#2980b9;text-decoration:none;font-weight:bold;">
                        {r.code.replace(".T", "")}
                    </a>
                </td>
                <td style="padding:7px 10px;border-bottom:1px solid #eee;">
                    {badges} {r.name}
                </td>
                <td style="padding:7px 10px;border-bottom:1px solid #eee;color:#666;font-size:12px;">
                    {r.market}
                </td>
                <td style="padding:7px 10px;border-bottom:1px solid #eee;text-align:right;
                    font-size:12px;">
                    {format_oku(r.market_cap)}億
                </td>
                <td style="padding:7px 10px;border-bottom:1px solid #eee;text-align:right;
                    font-weight:bold;color:{nc_color};">
                    {r.net_cash_ratio:.2f}{inv_note}
                </td>
                <td style="padding:7px 10px;border-bottom:1px solid #eee;text-align:right;">
                    {f"{r.cash_ratio:.0%}"}
                </td>
                <td style="padding:7px 10px;border-bottom:1px solid #eee;text-align:right;
                    color:#666;">
                    {f"{r.per:.1f}" if r.per else "-"}
                </td>
                <td style="padding:7px 10px;border-bottom:1px solid #eee;text-align:right;
                    font-size:12px;">
                    {f"{r.unit_cost / 10000:.1f}万" if r.unit_cost else "-"}
                </td>
                <td style="padding:7px 10px;border-bottom:1px solid #eee;color:#888;
                    font-size:12px;">
                    {r.sector}
                </td>
            </tr>
            """

        table = f"""
        <table style="width:100%;border-collapse:collapse;font-size:14px;">
            <thead>
                <tr style="background:#f0f0f0;font-size:12px;">
                    <th style="padding:8px 10px;text-align:left;">コード</th>
                    <th style="padding:8px 10px;text-align:left;">銘柄名</th>
                    <th style="padding:8px 10px;text-align:left;">市場</th>
                    <th style="padding:8px 10px;text-align:right;">時価総額</th>
                    <th style="padding:8px 10px;text-align:right;">NC比率</th>
                    <th style="padding:8px 10px;text-align:right;">現金比率</th>
                    <th style="padding:8px 10px;text-align:right;">PER</th>
                    <th style="padding:8px 10px;text-align:right;">単元</th>
                    <th style="padding:8px 10px;text-align:left;">業種</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
        """
    else:
        table = '<p style="color:#888;padding:20px 0;">該当銘柄なし</p>'

    primary_count = sum(1 for r in results if r.is_primary)
    legend = """
    <p style="font-size:12px;color:#666;margin:10px 0 20px 0;">
        <span style="background:#e74c3c;color:#fff;padding:1px 5px;border-radius:3px;font-size:11px;">本命</span>
        清原基準（ネットキャッシュ比率 ≥ 1.0 かつ PER ≤ 10）
        <span style="background:#95a5a6;color:#fff;padding:1px 5px;border-radius:3px;font-size:11px;">準</span>
        準候補（比率 0.7〜1.0 かつ PER ≤ 10）
        <span style="background:#9b59b6;color:#fff;padding:1px 5px;border-radius:3px;font-size:11px;">小型</span>
        時価総額100億未満
        &nbsp;<span style="color:#e67e22;">*</span>=投資有価証券データ欠損（比率は過小評価の可能性）
    </p>
    """

    stats_html = ""
    if stats:
        stats_html = f"""
        <div style="margin-top:20px;padding:10px;background:#f8f8f8;border-radius:5px;
            font-size:12px;color:#888;">
            スキャン銘柄数: {stats.get("total", "-")} /
            データ取得成功: {stats.get("fetched", "-")} /
            実行時間: {stats.get("duration", "-")}
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family:'Helvetica Neue',Arial,'Hiragino Sans',sans-serif;
        max-width:800px;margin:0 auto;padding:20px;color:#333;">
        <h1 style="color:#2c3e50;border-bottom:2px solid #2c3e50;padding-bottom:10px;
            font-size:20px;">
            清原達郎式 株スクリーニング　{today}
        </h1>
        <p style="color:#666;margin:5px 0;">
            該当: <strong>{len(results)}件</strong>
            うち本命: <strong style="color:#e74c3c;">{primary_count}件</strong>
            （ネットキャッシュ比率降順）
        </p>
        {legend}
        {table}
        {stats_html}
        <div style="margin-top:20px;padding:12px;background:#fff3cd;border-radius:5px;
            font-size:11px;color:#856404;">
            本スクリーニングは情報提供目的のみ。投資判断は自己責任で行ってください。
            データはyfinance経由で取得しており正確性を保証しません。
        </div>
    </body>
    </html>
    """
