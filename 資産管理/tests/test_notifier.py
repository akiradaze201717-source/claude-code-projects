"""notifier.py のユニットテスト。smtplib.SMTP を完全モックして実際のメール送信は発生しない。"""

import email
import email.header
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from notifier import (
    _make_html,
    notify_error,
    notify_import_summary,
    notify_incomplete_input,
    notify_weekly_committed,
    notify_weekly_remind,
    send_email,
)

GMAIL = "sender@gmail.com"
PASS = "app_pass"
TO = "receiver@example.com"


def _decode_msg(raw: str) -> tuple[str, str]:
    msg = email.message_from_string(raw)
    subject_parts = email.header.decode_header(msg["Subject"])
    subject = "".join(
        part.decode(enc or "utf-8") if isinstance(part, bytes) else part
        for part, enc in subject_parts
    )
    body = ""
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            payload = part.get_payload(decode=True)
            charset = part.get_content_charset() or "utf-8"
            body += payload.decode(charset)
    return subject, body


class TestMakeHtml:
    def test_title_in_h2(self):
        assert "<h2>タイトル</h2>" in _make_html("タイトル", [])

    def test_footer_included_when_given(self):
        html = _make_html("t", [], footer="補足事項")
        assert "補足事項" in html

    def test_no_footer_when_omitted(self):
        html = _make_html("t", [])
        assert "<p style=" not in html


class TestSendEmail:
    def test_smtp_connects_to_gmail(self):
        with patch("notifier.smtplib.SMTP") as MockSMTP:
            send_email("件名", "<p>本文</p>", GMAIL, PASS, TO)
        MockSMTP.assert_called_once_with("smtp.gmail.com", 587)

    def test_disabled_notify_is_noop(self):
        with patch("notifier.NOTIFY_ENABLED", False), patch("notifier.smtplib.SMTP") as MockSMTP:
            send_email("件名", "<p>本文</p>", GMAIL, PASS, TO)
        MockSMTP.assert_not_called()


class TestNotifyWeeklyRemind:
    def _call(self, **kwargs):
        with patch("notifier.smtplib.SMTP") as MockSMTP:
            server = MockSMTP.return_value.__enter__.return_value
            notify_weekly_remind(
                kwargs.get("template_path", "data/pending/残高入力.xlsx"),
                kwargs.get("gmo_balance", 152340.0),
                kwargs.get("missing", ["SBI証券"]),
                GMAIL,
                PASS,
                TO,
            )
            return _decode_msg(server.sendmail.call_args[0][2])

    def test_subject_mentions_reminder(self):
        subject, _ = self._call()
        assert "残高" in subject

    def test_body_contains_missing_account(self):
        _, body = self._call()
        assert "SBI証券" in body

    def test_body_handles_gmo_fetch_failure(self):
        _, body = self._call(gmo_balance=None)
        assert "取得失敗" in body


class TestNotifyIncompleteInput:
    def test_subject_and_body(self):
        with patch("notifier.smtplib.SMTP") as MockSMTP:
            server = MockSMTP.return_value.__enter__.return_value
            notify_incomplete_input(
                ["PayPay", "りそな銀行"], "data/pending/残高入力.xlsx", GMAIL, PASS, TO
            )
            subject, body = _decode_msg(server.sendmail.call_args[0][2])
        assert "未確定" in subject
        assert "PayPay" in body
        assert "りそな銀行" in body


class TestNotifyWeeklyCommitted:
    def test_body_contains_net_worth_and_categories(self):
        with patch("notifier.smtplib.SMTP") as MockSMTP:
            server = MockSMTP.return_value.__enter__.return_value
            notify_weekly_committed(
                "2026-08-31",
                1500000.0,
                30000.0,
                1470000.0,
                90000.0,
                [("食費", 12000.0), ("外食", 5000.0)],
                "reports/output/dashboard_latest.html",
                GMAIL,
                PASS,
                TO,
            )
            subject, body = _decode_msg(server.sendmail.call_args[0][2])
        assert "1,470,000" in subject
        assert "12,000" in body
        assert "食費" in body

    def test_first_commit_no_wow_change(self):
        with patch("notifier.smtplib.SMTP") as MockSMTP:
            server = MockSMTP.return_value.__enter__.return_value
            notify_weekly_committed(
                "2026-08-31",
                1500000.0,
                30000.0,
                1470000.0,
                None,
                [],
                "reports/output/dashboard_latest.html",
                GMAIL,
                PASS,
                TO,
            )
            _, body = _decode_msg(server.sendmail.call_args[0][2])
        assert "初回のため比較なし" in body


class TestNotifyImportSummary:
    def test_body_contains_counts(self):
        with patch("notifier.smtplib.SMTP") as MockSMTP:
            server = MockSMTP.return_value.__enter__.return_value
            notify_import_summary(12, 3, 2, GMAIL, PASS, TO)
            subject, body = _decode_msg(server.sendmail.call_args[0][2])
        assert "12" in subject
        assert "3" in body
        assert "2" in body


class TestNotifyError:
    def test_body_contains_message(self):
        with patch("notifier.smtplib.SMTP") as MockSMTP:
            server = MockSMTP.return_value.__enter__.return_value
            notify_error("何かが壊れた", GMAIL, PASS, TO)
            subject, body = _decode_msg(server.sendmail.call_args[0][2])
        assert "エラー" in subject
        assert "何かが壊れた" in body
