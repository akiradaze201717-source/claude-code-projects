"""Gmail 通知モジュール（資産管理用）。

gmo_dca/notifier.py の _make_html / send_email パターンを踏襲しつつ、
本プロジェクト用の通知関数を追加している。

gmo_dca では NOTIFY_ENABLED=False（DCA bot は自動売買のため通知を絞っている）だが、
資産管理は「週次リマインドメール」がワークフローの起点そのものなので True で運用する。
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

NOTIFY_ENABLED = True  # False にすると全ての send_email が no-op になる


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


def _make_html(title: str, rows: list[tuple[str, str]], footer: str = "") -> str:
    """シンプルなHTMLメール本文を生成。"""
    row_html = "".join(
        f"<tr><td style='padding:4px 12px;font-weight:bold'>{k}</td>"
        f"<td style='padding:4px 12px'>{v}</td></tr>"
        for k, v in rows
    )
    footer_html = (
        f"<p style='color:#888;font-size:12px;margin-top:16px'>{footer}</p>" if footer else ""
    )
    return (
        f"<html><body>"
        f"<h2>{title}</h2>"
        f"<table style='border-collapse:collapse'>{row_html}</table>"
        f"{footer_html}"
        f"</body></html>"
    )


def notify_weekly_remind(
    template_path: str,
    gmo_balance: float | None,
    missing_accounts: list[str],
    gmail_addr: str,
    gmail_pass: str,
    to_addr: str,
) -> None:
    """週次リマインド（入力テンプレート生成完了）を通知。"""
    subject = "[資産管理] 週次残高の入力をお願いします"
    gmo_row = (
        f"¥{gmo_balance:,.0f}"
        if gmo_balance is not None
        else "取得失敗（テンプレに手動記入してください）"
    )
    rows = [
        ("入力テンプレート", template_path),
        ("GMOコイン自動取得値", gmo_row),
        ("残り入力必要口座", "、".join(missing_accounts)),
    ]
    html = _make_html(
        "週次残高入力のお願い",
        rows,
        footer="Excelファイルの「今回残高」列を埋めてください。カード明細CSVは expenses/incoming/ 配下に配置すると次回コミット時に請求額が自動反映・取込・分類されます。",
    )
    send_email(subject, html, gmail_addr, gmail_pass, to_addr)


def notify_incomplete_input(
    missing_accounts: list[str], template_path: str, gmail_addr: str, gmail_pass: str, to_addr: str
) -> None:
    """コミット時に未入力口座があり確定できなかったことを通知。"""
    subject = "[資産管理] 未入力の口座があります — 今週分は未確定"
    rows = [
        ("未入力口座", "、".join(missing_accounts)),
        ("入力テンプレート", template_path),
    ]
    html = _make_html(
        "残高が未入力のため確定を見送りました",
        rows,
        footer="入力後に `python main.py commit` を再実行すると確定できます。",
    )
    send_email(subject, html, gmail_addr, gmail_pass, to_addr)


def notify_weekly_committed(
    snapshot_date: str,
    total_assets: float,
    total_liabilities: float,
    net_worth: float,
    wow_change: float | None,
    top_categories: list[tuple[str, float]],
    dashboard_path: str,
    gmail_addr: str,
    gmail_pass: str,
    to_addr: str,
) -> None:
    """週次スナップショット確定完了を通知。"""
    subject = f"[資産管理] {snapshot_date} 純資産 ¥{net_worth:,.0f} で確定"
    wow_disp = (
        f"{'+' if wow_change >= 0 else ''}¥{wow_change:,.0f}"
        if wow_change is not None
        else "初回のため比較なし"
    )
    rows = [
        ("純資産", f"¥{net_worth:,.0f}"),
        ("前週比", wow_disp),
        ("資産合計", f"¥{total_assets:,.0f}"),
        ("負債合計", f"¥{total_liabilities:,.0f}"),
    ]
    for cat, amount in top_categories:
        rows.append((f"支出({cat})", f"¥{amount:,.0f}"))
    rows.append(("ダッシュボード", dashboard_path))
    html = _make_html(f"{snapshot_date} 週次資産スナップショット確定", rows)
    send_email(subject, html, gmail_addr, gmail_pass, to_addr)


def notify_import_summary(
    imported_count: int,
    skipped_duplicate_count: int,
    uncategorized_count: int,
    gmail_addr: str,
    gmail_pass: str,
    to_addr: str,
) -> None:
    """カードCSV取込結果を通知。"""
    subject = f"[資産管理] 取引明細を{imported_count}件取込みました"
    rows = [
        ("新規取込", f"{imported_count}件"),
        ("重複スキップ", f"{skipped_duplicate_count}件"),
        ("未分類", f"{uncategorized_count}件"),
    ]
    html = _make_html(
        "支出明細CSV取込結果",
        rows,
        footer="未分類の取引は expenses/category_rules.json にキーワードを追加すると次回から自動分類されます。",
    )
    send_email(subject, html, gmail_addr, gmail_pass, to_addr)


def notify_error(error_message: str, gmail_addr: str, gmail_pass: str, to_addr: str) -> None:
    subject = "[資産管理] エラー発生"
    html = _make_html(
        "エラー",
        [
            ("詳細", error_message),
        ],
    )
    send_email(subject, html, gmail_addr, gmail_pass, to_addr)
