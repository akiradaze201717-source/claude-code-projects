"""
資産管理システム CLI

使い方:
  python main.py remind      # 週次リマインド: GMO自動取得+入力テンプレ生成+Gmail通知
  python main.py commit      # 週次コミット: テンプレ確定→カードCSV取込→台帳保存→ダッシュボード生成→Vault書き戻し→通知
  python main.py report      # 台帳の現状からダッシュボードのみ再生成（通知なし）
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    # Windows端末のcp932既定コードページでは ¥ 等の記号でUnicodeEncodeErrorになるため、
    # 出力をUTF-8に固定する（株/ir_digest/daily/buyback_daily.py と同じ対策）。
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / "config.env")

from balances.accounts import accounts_by_id, load_accounts
from balances.commit import IncompleteInputError, NoTemplateFoundError, commit_weekly_snapshot
from balances.gmo_client import GmoApi, GmoApiError
from balances.ledger import load_snapshots
from balances.template_builder import (
    build_weekly_template,
    fill_auto_values,
    find_latest_pending_template,
    missing_manual_accounts,
)
from expenses.billing_totals import fetch_card_billing_totals
from expenses.importer import run_import
from expenses.ledger import load_transactions
from log_setup import setup_logger
from notifier import (
    notify_error,
    notify_import_summary,
    notify_incomplete_input,
    notify_weekly_committed,
    notify_weekly_remind,
)
from reports.dashboard_builder import build_dashboard, expense_category_totals
from vault_writer import write_weekly_summary

JST = timezone(timedelta(hours=9))
setup_logger("asset_mgmt.log")
log = logging.getLogger(__name__)

REPORTS_OUTPUT_DIR = Path(__file__).parent / "reports" / "output"
VAULT_PATH_ENV = "OBSIDIAN_VAULT_PATH"


def _gmail_creds() -> tuple[str, str, str]:
    return (
        os.environ.get("GMAIL_ADDRESS", ""),
        os.environ.get("GMAIL_APP_PASSWORD", ""),
        os.environ.get("NOTIFY_TO_ADDRESS", ""),
    )


def _gmo_api() -> GmoApi | None:
    key = os.environ.get("GMO_API_KEY", "")
    secret = os.environ.get("GMO_API_SECRET", "")
    if not key or not secret:
        log.warning("GMO_API_KEY / GMO_API_SECRET が未設定 — GMOコイン残高は自動取得できません")
        return None
    return GmoApi(key, secret)


def _fetch_gmo_balances() -> tuple[float | None, float | None]:
    """(JPY現金残高, 暗号資産評価額) を返す。取得失敗時はそれぞれ None。"""
    api = _gmo_api()
    if api is None:
        return None, None

    jpy = None
    crypto = None
    try:
        jpy = api.get_available_amount()
    except GmoApiError as e:
        log.warning("GMO JPY残高の取得に失敗: %s", e)

    try:
        crypto = api.get_crypto_valuation_jpy()
    except GmoApiError as e:
        log.warning("GMO 暗号資産評価額の取得に失敗: %s", e)

    return jpy, crypto


def _build_and_save_dashboard() -> Path:
    accounts = accounts_by_id()
    snapshots = load_snapshots()
    transactions = load_transactions()
    html = build_dashboard(accounts, snapshots, transactions)

    REPORTS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(JST).strftime("%Y%m%d")
    dated_path = REPORTS_OUTPUT_DIR / f"dashboard_{today}.html"
    latest_path = REPORTS_OUTPUT_DIR / "dashboard_latest.html"
    dated_path.write_text(html, encoding="utf-8")
    latest_path.write_text(html, encoding="utf-8")
    log.info("ダッシュボード生成: %s", latest_path)

    # スマホから見られるよう、OneDrive等の同期フォルダにもコピーする（設定されていれば）
    sync_dir_str = os.environ.get("ASSET_SYNC_DIR", "")
    if sync_dir_str:
        try:
            sync_dir = Path(sync_dir_str)
            sync_dir.mkdir(parents=True, exist_ok=True)
            (sync_dir / "dashboard_latest.html").write_text(html, encoding="utf-8")
            log.info("ダッシュボードを同期フォルダへコピー: %s", sync_dir / "dashboard_latest.html")
        except Exception as e:
            log.error("ダッシュボードの同期フォルダへのコピーに失敗: %s", e)

    return latest_path


def cmd_remind(_args) -> int:
    accounts = load_accounts()
    gmail_addr, gmail_pass, to_addr = _gmail_creds()

    gmo_jpy, gmo_crypto = _fetch_gmo_balances()
    raw_date = datetime.now(JST).strftime("%Y%m%d")
    template_path = build_weekly_template(raw_date, accounts, gmo_jpy, gmo_crypto)

    # カードCSVが既にincoming/に置かれていれば請求額を自動反映（無くても後のcommit時に再挑戦する）
    card_totals = fetch_card_billing_totals()
    if card_totals:
        fill_auto_values(template_path, card_totals, accounts)

    missing = missing_manual_accounts(template_path, accounts)
    total_gmo = None
    if gmo_jpy is not None or gmo_crypto is not None:
        total_gmo = (gmo_jpy or 0.0) + (gmo_crypto or 0.0)

    if gmail_addr and gmail_pass and to_addr:
        notify_weekly_remind(
            str(template_path), total_gmo, missing, gmail_addr, gmail_pass, to_addr
        )
    else:
        log.warning("Gmail設定が不足 — 通知をスキップします")

    print(f"入力ファイル: {template_path}")
    if missing:
        print(f"未入力口座: {', '.join(missing)}")
    return 0


def cmd_commit(_args) -> int:
    accounts = load_accounts()
    gmail_addr, gmail_pass, to_addr = _gmail_creds()

    # 0) カード明細CSVから請求額合計を抽出し、テンプレートの空欄を自動で埋める。
    #    incoming/ のファイルが run_import() で processed/ へ移動される前に行う必要がある。
    template_path = find_latest_pending_template()
    if template_path is not None:
        card_totals = fetch_card_billing_totals()
        if card_totals:
            filled = fill_auto_values(template_path, card_totals, accounts)
            if filled:
                log.info("カードCSVから請求額を%d件自動反映しました", filled)

    # 1) カード明細CSVの取込（残高確定より先に行い、当該週の支出集計に反映させる）
    try:
        import_summary = run_import()
        log.info(
            "CSV取込: 新規%d件・重複%d件・未分類%d件",
            import_summary.imported_count,
            import_summary.skipped_duplicate_count,
            import_summary.uncategorized_count,
        )
        if (
            gmail_addr
            and gmail_pass
            and to_addr
            and (import_summary.imported_count or import_summary.failed_files)
        ):
            notify_import_summary(
                import_summary.imported_count,
                import_summary.skipped_duplicate_count,
                import_summary.uncategorized_count,
                gmail_addr,
                gmail_pass,
                to_addr,
            )
    except Exception as e:
        log.error("CSV取込中にエラー: %s", e)
        if gmail_addr and gmail_pass and to_addr:
            notify_error(f"CSV取込エラー: {e}", gmail_addr, gmail_pass, to_addr)

    # 2) 残高スナップショットの確定
    try:
        result = commit_weekly_snapshot(accounts=accounts)
    except NoTemplateFoundError:
        log.error(
            "確定対象の残高入力ファイルがありません。先に `python main.py remind` を実行してください。"
        )
        return 1
    except IncompleteInputError as e:
        log.warning("未入力口座のため確定を見送りました: %s", e.missing_accounts)
        if gmail_addr and gmail_pass and to_addr:
            notify_incomplete_input(
                e.missing_accounts, str(e.template_path), gmail_addr, gmail_pass, to_addr
            )
        return 1

    # 3) ダッシュボード生成
    dashboard_path = _build_and_save_dashboard()

    # 直近28日の支出カテゴリ集計（Vault書き戻し・通知の両方で使う）
    since = datetime.now(JST).date() - timedelta(days=28)
    category_totals = expense_category_totals(load_transactions(), since)

    # 4) Obsidian Vaultへの書き戻し
    vault_path_str = os.environ.get(VAULT_PATH_ENV, "")
    if vault_path_str:
        try:
            write_weekly_summary(
                Path(vault_path_str), result, accounts_by_id(), category_totals, str(dashboard_path)
            )
        except Exception as e:
            log.error("Obsidian Vaultへの書き戻しに失敗: %s", e)
    else:
        log.warning("%s が未設定 — Obsidian Vaultへの書き戻しをスキップします", VAULT_PATH_ENV)

    # 5) 通知
    if gmail_addr and gmail_pass and to_addr:
        notify_weekly_committed(
            result.snapshot_date,
            result.networth.total_assets,
            result.networth.total_liabilities,
            result.networth.net_worth,
            result.wow_change,
            category_totals[:3],
            str(dashboard_path),
            gmail_addr,
            gmail_pass,
            to_addr,
        )

    print(f"確定日: {result.snapshot_date}")
    print(f"純資産: ¥{result.networth.net_worth:,.0f}")
    print(f"ダッシュボード: {dashboard_path}")
    return 0


def cmd_report(_args) -> int:
    dashboard_path = _build_and_save_dashboard()
    print(f"ダッシュボード: {dashboard_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="資産管理システム")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("remind", help="週次リマインド（入力テンプレ生成+通知）")
    sub.add_parser("commit", help="週次コミット（台帳確定+ダッシュボード+Vault書き戻し）")
    sub.add_parser("report", help="ダッシュボードのみ再生成")
    args = parser.parse_args()

    handlers = {"remind": cmd_remind, "commit": cmd_commit, "report": cmd_report}
    try:
        return handlers[args.command](args)
    except Exception as e:
        log.exception("予期しないエラー")
        gmail_addr, gmail_pass, to_addr = _gmail_creds()
        if gmail_addr and gmail_pass and to_addr:
            notify_error(f"予期しないエラー: {e}", gmail_addr, gmail_pass, to_addr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
