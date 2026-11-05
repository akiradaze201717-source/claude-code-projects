"""Obsidian Vault(資産管理/週次サマリー/)への週次サマリー書き戻し。

金額のような決定的な数値をLLM生成(claude.exe --print)に委ねるとハルシネーション
リスクがあるため、本モジュールはPythonから直接frontmatter付きMarkdownをWriteする
（Vault側のscripts/generate_daily_tasks.ps1のようなLLM連携は使わない）。

frontmatterに net_worth 等の数値をプロパティとして持たせることで、Obsidian Bases
（資産管理.base）のformula機能で集計・前週比較ができるようにしている
（Vaultには Dataview は未導入のため）。
"""

import logging
from datetime import datetime
from pathlib import Path

from balances.accounts import ASSET, Account
from balances.commit import CommitResult

log = logging.getLogger(__name__)

SUMMARY_SUBDIR = "資産管理/週次サマリー"
DASHBOARD_NOTE_NAME = "資産管理/資産管理ダッシュボード.md"


def _safe_filename_date(date_str: str) -> str:
    return date_str  # 既に YYYY-MM-DD 形式想定


def write_weekly_summary(
    vault_path: Path,
    result: CommitResult,
    accounts: dict[str, Account],
    category_totals: list[tuple[str, float]],
    dashboard_html_path: str,
) -> Path:
    """週次サマリーノートをVaultへ書き込む。"""
    summary_dir = vault_path / SUMMARY_SUBDIR
    summary_dir.mkdir(parents=True, exist_ok=True)

    date_str = result.snapshot_date
    now_iso = datetime.now().astimezone().isoformat()
    wow = result.wow_change
    wow_disp = f"{'+' if wow >= 0 else ''}¥{wow:,.0f}" if wow is not None else "初回のため比較なし"

    asset_rows = ""
    liability_rows = ""
    for account_id, balance in sorted(result.networth.by_account.items()):
        account = accounts.get(account_id)
        name = account.name if account else account_id
        row = f"| {name} | ¥{balance:,.0f} |\n"
        if account and account.type == ASSET:
            asset_rows += row
        else:
            liability_rows += row

    category_rows = "".join(f"| {cat} | ¥{amount:,.0f} |\n" for cat, amount in category_totals[:10])
    if not category_rows:
        category_rows = "| （取引明細なし） | — |\n"

    body = f"""---
title: {date_str} 週次資産サマリー
dateCreated: {now_iso}
dateModified: {now_iso}
tags:
  - 資産管理
  - claude-analysis
net_worth: {result.networth.net_worth:.0f}
total_assets: {result.networth.total_assets:.0f}
total_liabilities: {result.networth.total_liabilities:.0f}
wow_change: {wow if wow is not None else "null"}
---

# {date_str} 週次資産サマリー

純資産: ¥{result.networth.net_worth:,.0f}（前週比 {wow_disp}）

## 資産内訳
| 口座 | 残高 |
|---|---|
{asset_rows}

## 負債内訳
| 口座 | 残高 |
|---|---|
{liability_rows}

## 支出カテゴリ別（直近）
| カテゴリ | 金額 |
|---|---|
{category_rows}

詳細ダッシュボード: `{dashboard_html_path}`
"""

    out_path = summary_dir / f"{_safe_filename_date(date_str)}_週次資産サマリー.md"
    out_path.write_text(body, encoding="utf-8")
    log.info("Vault週次サマリーを書き込み: %s", out_path)
    return out_path
