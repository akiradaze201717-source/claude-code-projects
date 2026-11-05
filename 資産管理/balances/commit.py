"""週次コミット処理のオーケストレーション。

data/pending/残高入力.xlsx（常に同じファイル名）の内容を確定し、残高台帳へ追記、
純資産計算、ダッシュボード生成、Obsidian Vaultへの書き戻しまでを行う。
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from balances.accounts import Account, accounts_by_id, load_accounts
from balances.ledger import append_snapshot, get_balances_for_date, list_snapshot_dates
from balances.networth import NetWorthResult, compute_networth, week_over_week_change
from balances.template_builder import (
    archive_and_reset,
    find_latest_pending_template,
    missing_manual_accounts,
    read_target_date,
    read_template_entries,
)

log = logging.getLogger(__name__)


class NoTemplateFoundError(Exception):
    """確定対象の残高入力ファイルが見つからない。"""


class IncompleteInputError(Exception):
    """未入力口座が残っており確定できない。"""

    def __init__(self, missing_accounts: list[str], template_path: Path):
        self.missing_accounts = missing_accounts
        self.template_path = template_path
        super().__init__(f"未入力口座あり: {missing_accounts}")


@dataclass(frozen=True)
class CommitResult:
    snapshot_date: str
    networth: NetWorthResult
    wow_change: float | None
    template_path: Path


def commit_weekly_snapshot(
    template_path: Path | None = None, accounts: list[Account] | None = None
) -> CommitResult:
    """残高入力ファイルを確定し台帳へ追記する。

    未入力口座があれば IncompleteInputError を送出して中断する（呼び出し元で通知）。
    """
    if template_path is None:
        template_path = find_latest_pending_template()
    if template_path is None or not template_path.exists():
        raise NoTemplateFoundError("data/pending/残高入力.xlsx が見つかりません")

    if accounts is None:
        accounts = load_accounts()

    missing = missing_manual_accounts(template_path, accounts)
    if missing:
        raise IncompleteInputError(missing, template_path)

    date_str = read_target_date(template_path)
    entries = read_template_entries(template_path, accounts)

    # 純資産計算（前回確定日との比較用に、追記前の台帳から前回値を取っておく）
    prior_dates = [d for d in list_snapshot_dates() if d < date_str]
    previous_result = None
    if prior_dates:
        prev_date = prior_dates[-1]
        prev_entries = list(get_balances_for_date(prev_date).values())
        previous_result = compute_networth(prev_date, prev_entries, accounts_by_id())

    append_snapshot(date_str, entries)

    current_entries = list(get_balances_for_date(date_str).values())
    current_result = compute_networth(date_str, current_entries, accounts_by_id())
    wow = week_over_week_change(current_result, previous_result)

    # 確定内容をarchiveへ日付付きでコピー保存し、入力欄をリセット（ライブファイルは使い回す）
    archived_path = archive_and_reset(template_path, date_str)

    return CommitResult(
        snapshot_date=date_str,
        networth=current_result,
        wow_change=wow,
        template_path=archived_path,
    )
