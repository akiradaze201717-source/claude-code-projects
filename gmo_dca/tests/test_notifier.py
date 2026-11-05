"""
notifier.py のユニットテスト

smtplib.SMTP を完全モックして実際のメール送信は発生しない。
"""

import email
import email.header
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from notifier import (
    _make_html,
    notify_already_purchased,
    notify_balance_insufficient,
    notify_error,
    notify_purchase,
    notify_rsi_skip,
    send_email,
)

GMAIL = "sender@gmail.com"
PASS = "app_pass"
TO = "receiver@example.com"


def _decode_msg(raw: str) -> tuple[str, str]:
    """sendmail の第3引数（raw MIME文字列）から subject と body を decoded で返す。"""
    msg = email.message_from_string(raw)

    # Subject: RFC2047デコード
    subject_parts = email.header.decode_header(msg["Subject"])
    subject = "".join(
        part.decode(enc or "utf-8") if isinstance(part, bytes) else part
        for part, enc in subject_parts
    )

    # Body: base64 or quoted-printable → str
    body = ""
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            payload = part.get_payload(decode=True)  # bytes
            charset = part.get_content_charset() or "utf-8"
            body += payload.decode(charset)

    return subject, body


# ============================================================
# _make_html — 純粋関数
# ============================================================


class TestMakeHtml:
    def test_title_in_h2(self):
        html = _make_html("テストタイトル", [])
        assert "<h2>テストタイトル</h2>" in html

    def test_rows_in_td(self):
        html = _make_html("title", [("キー", "値")])
        assert "キー" in html
        assert "値" in html

    def test_empty_rows(self):
        html = _make_html("title", [])
        assert "<h2>title</h2>" in html
        assert "<html>" in html

    def test_multiple_rows(self):
        rows = [("A", "1"), ("B", "2"), ("C", "3")]
        html = _make_html("t", rows)
        for k, v in rows:
            assert k in html
            assert v in html

    def test_returns_valid_html_structure(self):
        html = _make_html("t", [])
        assert html.startswith("<html>")
        assert html.endswith("</html>")


# ============================================================
# send_email — smtplib.SMTP をモック
# ============================================================


class TestSendEmail:
    def _send(self, smtp_mock):
        send_email("件名", "<p>本文</p>", GMAIL, PASS, TO)

    def test_starttls_called(self):
        with patch("notifier.smtplib.SMTP") as MockSMTP:
            server = MockSMTP.return_value.__enter__.return_value
            self._send(server)
        server.starttls.assert_called_once()

    def test_login_called_with_credentials(self):
        with patch("notifier.smtplib.SMTP") as MockSMTP:
            server = MockSMTP.return_value.__enter__.return_value
            self._send(server)
        server.login.assert_called_once_with(GMAIL, PASS)

    def test_sendmail_called_with_correct_addresses(self):
        with patch("notifier.smtplib.SMTP") as MockSMTP:
            server = MockSMTP.return_value.__enter__.return_value
            self._send(server)
        args = server.sendmail.call_args[0]
        assert args[0] == GMAIL
        assert args[1] == TO

    def test_smtp_connects_to_gmail(self):
        with patch("notifier.smtplib.SMTP") as MockSMTP:
            self._send(None)
        MockSMTP.assert_called_once_with("smtp.gmail.com", 587)

    def test_call_order_starttls_login_sendmail(self):
        """starttls → login → sendmail の順で呼ばれる"""
        with patch("notifier.smtplib.SMTP") as MockSMTP:
            server = MockSMTP.return_value.__enter__.return_value
            manager = MagicMock()
            server.starttls = manager.starttls
            server.login = manager.login
            server.sendmail = manager.sendmail
            self._send(server)
        calls = [c[0] for c in manager.mock_calls]
        assert calls.index("starttls") < calls.index("login")
        assert calls.index("login") < calls.index("sendmail")


# ============================================================
# notify_purchase
# ============================================================


class TestNotifyPurchase:
    def _call(self):
        with patch("notifier.smtplib.SMTP") as MockSMTP:
            server = MockSMTP.return_value.__enter__.return_value
            notify_purchase("BTC", "0.0005", 10_000_000.0, 5000, 45.0, GMAIL, PASS, TO)
            return _decode_msg(server.sendmail.call_args[0][2])

    def test_send_email_called(self):
        with patch("notifier.smtplib.SMTP") as MockSMTP:
            server = MockSMTP.return_value.__enter__.return_value
            notify_purchase("BTC", "0.0005", 10_000_000.0, 5000, 45.0, GMAIL, PASS, TO)
        server.sendmail.assert_called_once()

    def test_subject_contains_symbol_and_keyword(self):
        subject, _ = self._call()
        assert "BTC" in subject
        assert "購入完了" in subject

    def test_body_contains_size(self):
        _, body = self._call()
        assert "0.0005" in body

    def test_body_contains_rsi(self):
        _, body = self._call()
        assert "45.0" in body


# ============================================================
# notify_rsi_skip
# ============================================================


class TestNotifyRsiSkip:
    def _call(self):
        with patch("notifier.smtplib.SMTP") as MockSMTP:
            server = MockSMTP.return_value.__enter__.return_value
            notify_rsi_skip("ETH", 72.5, GMAIL, PASS, TO)
            return _decode_msg(server.sendmail.call_args[0][2])

    def test_subject_contains_rsi_value(self):
        subject, _ = self._call()
        assert "72.5" in subject
        assert "RSI" in subject

    def test_subject_contains_symbol(self):
        subject, _ = self._call()
        assert "ETH" in subject


# ============================================================
# notify_already_purchased
# ============================================================


class TestNotifyAlreadyPurchased:
    def _call(self):
        with patch("notifier.smtplib.SMTP") as MockSMTP:
            server = MockSMTP.return_value.__enter__.return_value
            notify_already_purchased("BTC", GMAIL, PASS, TO)
            return _decode_msg(server.sendmail.call_args[0][2])

    def test_subject_contains_purchased_keyword(self):
        subject, _ = self._call()
        assert "購入済み" in subject

    def test_subject_contains_symbol(self):
        subject, _ = self._call()
        assert "BTC" in subject


# ============================================================
# notify_balance_insufficient
# ============================================================


class TestNotifyBalanceInsufficient:
    def _call(self):
        with patch("notifier.smtplib.SMTP") as MockSMTP:
            server = MockSMTP.return_value.__enter__.return_value
            notify_balance_insufficient("BTC", 5000, 1234.0, GMAIL, PASS, TO)
            return _decode_msg(server.sendmail.call_args[0][2])

    def test_subject_contains_balance_keyword(self):
        subject, _ = self._call()
        assert "残高不足" in subject

    def test_body_contains_required_and_available(self):
        _, body = self._call()
        assert "5,000" in body
        assert "1,234" in body


# ============================================================
# notify_error
# ============================================================


class TestNotifyError:
    def _call(self):
        with patch("notifier.smtplib.SMTP") as MockSMTP:
            server = MockSMTP.return_value.__enter__.return_value
            notify_error("Something went wrong", GMAIL, PASS, TO)
            return _decode_msg(server.sendmail.call_args[0][2])

    def test_subject_is_error(self):
        subject, _ = self._call()
        assert "エラー" in subject

    def test_body_contains_error_message(self):
        _, body = self._call()
        assert "Something went wrong" in body
