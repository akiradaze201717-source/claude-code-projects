"""純資産（資産合計 − 負債合計）の計算ロジック。"""

from dataclasses import dataclass

from balances.accounts import ASSET, LIABILITY, Account


@dataclass(frozen=True)
class NetWorthResult:
    date: str
    total_assets: float
    total_liabilities: float
    net_worth: float
    by_account: dict[str, float]  # account_id -> balance


def compute_networth(
    date_str: str, snapshot_entries: list[dict], accounts: dict[str, Account]
) -> NetWorthResult:
    """指定日のスナップショット群（同一date想定）から純資産を計算する。

    accounts に存在しない account_id のエントリは無視する（口座マスタ変更への耐性）。
    """
    total_assets = 0.0
    total_liabilities = 0.0
    by_account: dict[str, float] = {}

    for entry in snapshot_entries:
        account = accounts.get(entry["account_id"])
        if account is None:
            continue
        balance = float(entry["balance"])
        by_account[account.id] = balance
        if account.type == ASSET:
            total_assets += balance
        elif account.type == LIABILITY:
            total_liabilities += balance

    return NetWorthResult(
        date=date_str,
        total_assets=total_assets,
        total_liabilities=total_liabilities,
        net_worth=total_assets - total_liabilities,
        by_account=by_account,
    )


def week_over_week_change(current: NetWorthResult, previous: NetWorthResult | None) -> float | None:
    """前回スナップショットとの純資産の差分。前回が無ければ None（初回）。"""
    if previous is None:
        return None
    return current.net_worth - previous.net_worth
