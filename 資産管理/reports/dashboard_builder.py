"""資産管理ダッシュボード（HTML）の生成。

株/ir_digest/daily/buyback_report_html.py と同じ「外部テンプレートエンジン無し、
インラインCSSの自己完結f-string HTML」方式。グラフ描画はChart.jsをCDN経由で読み込む
（自前でSVGグラフを作るより保守コストが低いため）。オフライン運用が必須になった場合は
reports/vendor/chart.umd.min.js を同梱する代替案に切り替え可能。
"""

import html as _html
import json
from collections import defaultdict
from datetime import date, datetime, timedelta

from balances.accounts import ASSET, Account
from balances.networth import compute_networth
from expenses.category_rules import UNCATEGORIZED

CHART_JS_CDN = "https://cdn.jsdelivr.net/npm/chart.js@4"
RECENT_EXPENSE_WINDOW_DAYS = 28
RECENT_TRANSACTIONS_LIMIT = 25


def _networth_series(snapshots: list[dict], accounts: dict[str, Account]) -> list[dict]:
    by_date: dict[str, list[dict]] = defaultdict(list)
    for entry in snapshots:
        by_date[entry["date"]].append(entry)

    series = []
    for date_str in sorted(by_date.keys()):
        result = compute_networth(date_str, by_date[date_str], accounts)
        series.append(
            {
                "date": date_str,
                "total_assets": result.total_assets,
                "total_liabilities": result.total_liabilities,
                "net_worth": result.net_worth,
            }
        )
    return series


def _current_breakdown(
    snapshots: list[dict], accounts: dict[str, Account]
) -> tuple[str, list[dict]]:
    if not snapshots:
        return "", []
    latest_date = max(e["date"] for e in snapshots)
    latest_entries = [e for e in snapshots if e["date"] == latest_date]
    rows = []
    for e in sorted(latest_entries, key=lambda x: x["account_id"]):
        account = accounts.get(e["account_id"])
        rows.append(
            {
                "name": account.name if account else e["account_id"],
                "type": account.type if account else "asset",
                "balance": e["balance"],
            }
        )
    return latest_date, rows


def expense_category_totals(transactions: list[dict], since: date) -> list[tuple[str, float]]:
    totals: dict[str, float] = defaultdict(float)
    for t in transactions:
        txn_date = datetime.fromisoformat(t["txn_date"]).date()
        if txn_date < since:
            continue
        totals[t["category"]] += t["amount"]
    return sorted(totals.items(), key=lambda kv: -kv[1])


def build_dashboard(
    accounts: dict[str, Account],
    snapshots: list[dict],
    transactions: list[dict],
    generated_at: datetime | None = None,
) -> str:
    generated_at = generated_at or datetime.now()
    series = _networth_series(snapshots, accounts)
    latest_date, breakdown_rows = _current_breakdown(snapshots, accounts)

    since = generated_at.date() - timedelta(days=RECENT_EXPENSE_WINDOW_DAYS)
    category_totals = expense_category_totals(transactions, since)

    recent_txns = sorted(transactions, key=lambda t: t["txn_date"], reverse=True)[
        :RECENT_TRANSACTIONS_LIMIT
    ]

    latest = series[-1] if series else None
    prev = series[-2] if len(series) >= 2 else None
    net_worth_disp = f"¥{latest['net_worth']:,.0f}" if latest else "データなし"
    wow_disp = ""
    if latest and prev:
        diff = latest["net_worth"] - prev["net_worth"]
        sign = "+" if diff >= 0 else ""
        color = "#2e7d32" if diff >= 0 else "#c62828"
        wow_disp = f'<span style="color:{color};font-size:16px;">(前週比 {sign}¥{diff:,.0f})</span>'

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>資産管理ダッシュボード</title>
  <script src="{CHART_JS_CDN}"></script>
</head>
<body style="font-family:'Helvetica Neue',Arial,'Hiragino Sans','Yu Gothic',sans-serif;
    max-width:960px;margin:0 auto;padding:20px;color:#2c3e50;background:#fff;">

  <h1 style="border-bottom:3px solid #2980b9;padding-bottom:10px;font-size:22px;">
    💰 資産管理ダッシュボード
  </h1>
  <p style="color:#666;font-size:12px;">生成日時: {generated_at.strftime("%Y-%m-%d %H:%M")}（最新スナップショット: {latest_date or "—"}）</p>

  <div style="padding:18px 22px;background:#f0f7fc;border-radius:10px;margin:16px 0;">
    <div style="font-size:13px;color:#888;">純資産</div>
    <div style="font-size:32px;font-weight:bold;color:#2980b9;">{net_worth_disp} {wow_disp}</div>
  </div>

  <h2 style="font-size:16px;border-left:5px solid #2980b9;padding-left:8px;">純資産の推移</h2>
  <canvas id="networthChart" height="90"></canvas>

  <h2 style="font-size:16px;border-left:5px solid #2980b9;padding-left:8px;margin-top:28px;">資産・負債の内訳（{latest_date or "—"}）</h2>
  {_build_breakdown_table(breakdown_rows)}

  <h2 style="font-size:16px;border-left:5px solid #2980b9;padding-left:8px;margin-top:28px;">支出カテゴリ別（直近{RECENT_EXPENSE_WINDOW_DAYS}日）</h2>
  <canvas id="categoryChart" height="110"></canvas>

  <h2 style="font-size:16px;border-left:5px solid #2980b9;padding-left:8px;margin-top:28px;">最近の取引明細</h2>
  {_build_transactions_table(recent_txns)}

  <div style="margin-top:28px;padding:12px;background:#fff3cd;border-radius:6px;font-size:11px;color:#856404;">
    本ダッシュボードは個人の記録用であり、第三者への開示を想定していません。
    支出カテゴリは expenses/category_rules.json のキーワード一致による自動分類です。「未分類」は精度向上のためルールを育ててください。
  </div>

  <script>
    const networthData = {json.dumps(series, ensure_ascii=False)};
    new Chart(document.getElementById('networthChart'), {{
      type: 'line',
      data: {{
        labels: networthData.map(d => d.date),
        datasets: [
          {{ label: '資産合計', data: networthData.map(d => d.total_assets), borderColor: '#27ae60', tension: 0.2 }},
          {{ label: '負債合計', data: networthData.map(d => d.total_liabilities), borderColor: '#c0392b', tension: 0.2 }},
          {{ label: '純資産', data: networthData.map(d => d.net_worth), borderColor: '#2980b9', borderWidth: 3, tension: 0.2 }}
        ]
      }},
      options: {{ scales: {{ y: {{ ticks: {{ callback: v => '¥' + v.toLocaleString() }} }} }} }}
    }});

    const categoryData = {json.dumps(category_totals, ensure_ascii=False)};
    new Chart(document.getElementById('categoryChart'), {{
      type: 'bar',
      data: {{
        labels: categoryData.map(d => d[0]),
        datasets: [{{ label: '支出額', data: categoryData.map(d => d[1]), backgroundColor: '#5dade2' }}]
      }},
      options: {{ indexAxis: 'y', scales: {{ x: {{ ticks: {{ callback: v => '¥' + v.toLocaleString() }} }} }} }}
    }});
  </script>
</body>
</html>"""


def _build_breakdown_table(rows: list[dict]) -> str:
    if not rows:
        return '<div style="color:#888;font-size:13px;">まだスナップショットがありません。</div>'
    body = ""
    for r in rows:
        color = "#27ae60" if r["type"] == ASSET else "#c0392b"
        label = "資産" if r["type"] == ASSET else "負債"
        body += f"""
        <tr>
          <td style="padding:6px 10px;border-bottom:1px solid #eee;">{_html.escape(r["name"])}</td>
          <td style="padding:6px 10px;border-bottom:1px solid #eee;color:{color};font-size:11px;">{label}</td>
          <td style="padding:6px 10px;border-bottom:1px solid #eee;text-align:right;">¥{r["balance"]:,.0f}</td>
        </tr>"""
    return f"""
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <thead><tr style="background:#f4f8fb;font-size:11px;">
        <th style="padding:6px 10px;text-align:left;">口座</th>
        <th style="padding:6px 10px;text-align:left;">区分</th>
        <th style="padding:6px 10px;text-align:right;">残高</th>
      </tr></thead>
      <tbody>{body}</tbody>
    </table>"""


def _build_transactions_table(transactions: list[dict]) -> str:
    if not transactions:
        return '<div style="color:#888;font-size:13px;">取引明細はまだありません。</div>'
    body = ""
    for t in transactions:
        is_uncategorized = t["category"] == UNCATEGORIZED
        cat_style = "color:#c0392b;font-weight:bold;" if is_uncategorized else "color:#555;"
        body += f"""
        <tr>
          <td style="padding:5px 9px;border-bottom:1px solid #f0f0f0;font-size:11px;color:#888;">{t["txn_date"]}</td>
          <td style="padding:5px 9px;border-bottom:1px solid #f0f0f0;">{_html.escape(t["description"])}</td>
          <td style="padding:5px 9px;border-bottom:1px solid #f0f0f0;{cat_style}">{_html.escape(t["category"])}</td>
          <td style="padding:5px 9px;border-bottom:1px solid #f0f0f0;text-align:right;">¥{t["amount"]:,.0f}</td>
        </tr>"""
    return f"""
    <table style="width:100%;border-collapse:collapse;font-size:12px;">
      <thead><tr style="background:#f4f8fb;font-size:11px;">
        <th style="padding:5px 9px;text-align:left;">日付</th>
        <th style="padding:5px 9px;text-align:left;">摘要</th>
        <th style="padding:5px 9px;text-align:left;">カテゴリ</th>
        <th style="padding:5px 9px;text-align:right;">金額</th>
      </tr></thead>
      <tbody>{body}</tbody>
    </table>"""
