"""🔔新規自社株買い発表の株価反応・答え合わせ（週次自動更新）。

daily/buyback_daily.py が毎日更新する共有の恒久台帳
../buyback_events_archive.json からイベント一覧を読み込み（backtestは
台帳を読むだけ・daily側のHTML出力には一切依存しない）、各社の株価を
yfinanceで取得してTOPIX（連動ETF 1306.T で代替）比の超過リターンを算出する。

基準日（day0）= 発表日の翌営業日の終値（IR発表は引け後が多いため、
発表を見てから動ける最初のタイミングを基準にする）。
1週間/2週間/3週間/1ヶ月/2ヶ月/3ヶ月/6ヶ月/1年/2年後（基準日からの暦日ベース、
その日以降最初の取引日）を比較する（短期は細かく・長期は粗く）。
あわせて、発表の種類・時価総額・自社株買い規模（発行済比率）等とリターンの
相関・グループ比較も行う。

※ 集計対象は2026-06-02以降の発表分のみ（🔔検知を入れた日）。2年ホライゾンが
実際に埋まるのは2028年半ば以降で、それまでは新しい発表ほど長期ホライゾンが
「経過待ち」表示のまま。過去分の遡及取得はせず、今後の発表分で自然に蓄積する。

出力: output/buyback_backtest.html（毎回上書き）。RECIPIENT_EMAIL へ送信。
使い方:
  python buyback_backtest.py            # 集計してHTML生成・送信
  python buyback_backtest.py --no-send  # 送信せずHTMLのみ生成
"""

import argparse
import io
import json
import logging
import os
import re
import statistics as st
import sys
import time
import warnings
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

warnings.filterwarnings("ignore")
SCRIPT_DIR = Path(__file__).resolve().parent  # .../ir_digest/backtest
ROOT_DIR = SCRIPT_DIR.parent  # .../ir_digest （共有リソース置き場）
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(ROOT_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import email_sender  # ROOT_DIR直下の共有モジュール
import pandas as pd
import pypdf
import requests
import yfinance as yf
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
)
logger = logging.getLogger("buyback_backtest")
# 短期は細かく・長期になるほど粗く（最大2年）。暦日換算（月=30日、年=365日）。
HORIZONS = [
    ("1週間", 7),
    ("2週間", 14),
    ("3週間", 21),
    ("1ヶ月", 30),
    ("2ヶ月", 60),
    ("3ヶ月", 90),
    ("6ヶ月", 182),
    ("1年", 365),
    ("2年", 730),
]
# 個別ミニチャートは短期のみ表示（HTML軽量化のため）。数値表は全ホライゾン長期化。
CHART_DAYS = 33
TOPIX_PROXY = "1306.T"  # NEXT FUNDS TOPIX ETF（TOPIX指数そのものはyfinance非対応）
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ir_digest/1.0"}


# ---------------------------------------------------------------------------
# ① イベント読み込み（daily/buyback_daily.py が更新する共有台帳を読むだけ。
#    backtestはdaily側のHTML出力に一切依存しない＝フォルダを分けても安全）
# ---------------------------------------------------------------------------
ARCHIVE_PATH = ROOT_DIR / "buyback_events_archive.json"


def load_events(start_date: str) -> list[dict]:
    if not ARCHIVE_PATH.exists():
        logger.warning("イベント台帳が見つかりません: %s", ARCHIVE_PATH)
        return []
    archive = json.loads(ARCHIVE_PATH.read_text(encoding="utf-8"))
    uniq = [e for e in archive if e["date"] >= start_date]
    uniq.sort(key=lambda e: (e["date"], e["code"]))
    return uniq


# ---------------------------------------------------------------------------
# ② 株価取得・リターン計算（TOPIX比）
# ---------------------------------------------------------------------------
def nearest_on_or_after(series: pd.Series, target_date):
    series = series.dropna()
    idx = series.index[series.index >= pd.Timestamp(target_date)]
    if len(idx) == 0:
        return None, None
    d = idx[0]
    return d, series.loc[d]


def compute_returns(events: list[dict], start_date: str) -> tuple[list[dict], list[dict]]:
    today = datetime.now().date()
    start = datetime.strptime(start_date, "%Y%m%d").date() - timedelta(days=5)
    end = today + timedelta(days=2)

    topix = yf.Ticker(TOPIX_PROXY).history(start=start.isoformat(), end=end.isoformat())
    topix.index = topix.index.tz_localize(None).normalize()
    topix_close = topix["Close"]

    results, skipped = [], []
    price_cache: dict[str, pd.Series | None] = {}

    for i, ev in enumerate(events):
        code, date_s = ev["code"], ev["date"]
        ann_date = datetime.strptime(date_s, "%Y%m%d").date()

        if code not in price_cache:
            try:
                h = yf.Ticker(f"{code}.T").history(
                    start=(ann_date - timedelta(days=5)).isoformat(), end=end.isoformat()
                )
                if h.empty:
                    price_cache[code] = None
                else:
                    h.index = h.index.tz_localize(None).normalize()
                    close = h["Close"]
                    price_cache[code] = close[~close.index.duplicated()]
            except Exception:
                price_cache[code] = None

        close = price_cache[code]
        if close is None or close.empty:
            skipped.append({**ev, "reason": "株価データ取得不可"})
            continue

        d0, p0 = nearest_on_or_after(close, ann_date + timedelta(days=1))
        if d0 is None:
            skipped.append({**ev, "reason": "翌営業日の株価なし（データ末尾）"})
            continue
        td0, tp0 = nearest_on_or_after(topix_close, ann_date + timedelta(days=1))
        if td0 is None:
            skipped.append({**ev, "reason": "翌営業日のTOPIXデータなし"})
            continue

        row = {
            **ev,
            "base_date": d0.strftime("%Y-%m-%d"),
            "base_price": round(float(p0), 1),
            "series": [],
            "returns": {},
        }

        ser_end = min(close.index.max(), pd.Timestamp(d0) + pd.Timedelta(days=CHART_DAYS))
        ser = close[(close.index >= d0) & (close.index <= ser_end)]
        tser = topix_close[(topix_close.index >= td0) & (topix_close.index <= ser_end)]
        for dt, v in ser.items():
            tv = None
            sub = tser[tser.index <= dt]
            if not sub.empty:
                tv = round(float(sub.iloc[-1]) / float(tp0) * 100, 2)
            row["series"].append(
                {
                    "date": dt.strftime("%Y-%m-%d"),
                    "stock_idx": round(float(v) / float(p0) * 100, 2),
                    "topix_idx": tv,
                }
            )

        for label, days in HORIZONS:
            target = d0.date() + timedelta(days=days)
            if today < target:
                row["returns"][label] = None
                continue
            d1, p1 = nearest_on_or_after(close, target)
            if d1 is None:
                row["returns"][label] = None
                continue
            td1, tp1 = nearest_on_or_after(topix_close, target)
            stock_ret = (float(p1) / float(p0) - 1) * 100
            adj_ret = None
            if td1 is not None:
                idx_ret = (float(tp1) / float(tp0) - 1) * 100
                adj_ret = stock_ret - idx_ret
            row["returns"][label] = {
                "raw": round(stock_ret, 2),
                "adjusted": round(adj_ret, 2) if adj_ret is not None else None,
                "as_of": d1.strftime("%Y-%m-%d"),
            }

        results.append(row)
        if (i + 1) % 30 == 0:
            logger.info("株価取得: %d/%d", i + 1, len(events))

    return results, skipped


# ---------------------------------------------------------------------------
# ③ 追加ファクター（発表種類・時価総額・自社株買い規模）
# ---------------------------------------------------------------------------
def classify_subtype(title: str) -> str:
    if "取得枠設定" in title:
        return "新規枠設定"
    if "事項の決定" in title or "事項の一部変更" in title:
        return "事項決定"
    if "立会外" in title or "ToSTNeT" in title or "ＴｏＳＴＮｅＴ" in title or "買付" in title:
        return "買付(ToSTNeT等)"
    if "市場買付" in title:
        return "市場買付"
    return "その他"


def enrich_factors(events: list[dict]) -> dict:
    """(date, code) -> {subtype, market_cap_oku, buyback_ratio_pct}"""
    mcap_cache: dict[str, float | None] = {}
    factors = {}
    for ev in events:
        code, pdf_url, title = ev["code"], ev.get("pdf_url"), ev["title"]
        if code not in mcap_cache:
            mcap = None
            if re.fullmatch(r"\d{4}", code):
                try:
                    info = yf.Ticker(f"{code}.T").info
                    mc = info.get("marketCap")
                    mcap = mc / 1e8 if mc else None
                except Exception:
                    pass
                time.sleep(0.1)
            mcap_cache[code] = mcap

        amt = ratio = None
        if pdf_url:
            try:
                r = requests.get(pdf_url, headers=UA, timeout=25)
                rd = pypdf.PdfReader(io.BytesIO(r.content))
                t = "".join(re.sub(r"\s+", "", (p.extract_text() or "")) for p in rd.pages[:3])
                ma = re.search(r"取得価額の?総額([0-9,]+)円", t)
                if ma:
                    amt = int(ma.group(1).replace(",", "")) / 1e8
                mr = re.search(r"割合([0-9.]+)[％%]", t)
                if mr:
                    ratio = float(mr.group(1))
            except Exception:
                pass

        mcap = mcap_cache[code]
        implied_ratio = (amt / mcap * 100) if (amt and mcap) else None
        factors[(ev["date"], code)] = {
            "subtype": classify_subtype(title),
            "market_cap_oku": mcap,
            "buyback_amt_oku": amt,
            "buyback_ratio_pct": ratio if ratio is not None else implied_ratio,
        }
    return factors


# ---------------------------------------------------------------------------
# ④ 相関・グループ分析
# ---------------------------------------------------------------------------
def pearson(pairs):
    pairs = [(x, y) for x, y in pairs if x is not None and y is not None]
    n = len(pairs)
    if n < 5:
        return None, n
    xs, ys = zip(*pairs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in pairs)
    sx = (sum((x - mx) ** 2 for x in xs)) ** 0.5
    sy = (sum((y - my) ** 2 for y in ys)) ** 0.5
    if sx == 0 or sy == 0:
        return None, n
    return cov / (sx * sy), n


def build_correlation_analysis(results: list[dict], factors: dict) -> dict:
    merged = []
    for r in results:
        f = factors.get((r["date"], r["code"]))
        if f is None:
            continue
        ret_1w = r["returns"].get("1週間", {}).get("raw") if r["returns"].get("1週間") else None
        ret_1mo = r["returns"].get("1ヶ月", {}).get("raw") if r["returns"].get("1ヶ月") else None
        merged.append(
            {
                **f,
                "code": r["code"],
                "company": r["company"],
                "sector": r["sector"],
                "date": r["date"],
                "dow": datetime.strptime(r["date"], "%Y%m%d").strftime("%a"),
                "ret_1w": ret_1w,
                "ret_1mo": ret_1mo,
            }
        )

    corr_ratio, n_ratio = pearson([(m["buyback_ratio_pct"], m["ret_1w"]) for m in merged])
    corr_mcap, n_mcap = pearson([(m["market_cap_oku"], m["ret_1w"]) for m in merged])

    def group_stats(key, horizon_key="ret_1w", min_n=3):
        by = defaultdict(list)
        for m in merged:
            if m[horizon_key] is not None and m.get(key):
                by[m[key]].append(m[horizon_key])
        out = [
            {
                "label": k,
                "n": len(v),
                "avg": st.mean(v),
                "median": st.median(v),
                "win": sum(1 for x in v if x > 0) / len(v) * 100,
            }
            for k, v in by.items()
            if len(v) >= min_n
        ]
        out.sort(key=lambda x: -x["avg"])
        return out

    dow_order = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4}
    dow_stats = group_stats("dow", min_n=1)
    dow_stats.sort(key=lambda x: dow_order.get(x["label"], 9))

    return {
        "corr_ratio": corr_ratio,
        "n_ratio": n_ratio,
        "corr_mcap": corr_mcap,
        "n_mcap": n_mcap,
        "by_subtype": group_stats("subtype"),
        "by_sector": group_stats("sector"),
        "by_dow": dow_stats,
        "n_merged": len(merged),
    }


# ---------------------------------------------------------------------------
# ⑤ HTMLレポート生成
# ---------------------------------------------------------------------------
def fmt_pct(v, none="—"):
    if v is None:
        return none
    color = "#3ecf8e" if v >= 0 else "#ff6b6b"
    return f'<span style="color:{color};font-weight:bold;">{v:+.1f}%</span>'


def build_html(results, skipped, corr, week_disp: str) -> str:
    HZ = [h for h, _ in HORIZONS]

    summary = {}
    for h in HZ:
        raws = [r["returns"][h]["raw"] for r in results if r["returns"].get(h)]
        adjs = [
            r["returns"][h]["adjusted"]
            for r in results
            if r["returns"].get(h) and r["returns"][h]["adjusted"] is not None
        ]
        if raws:
            summary[h] = {
                "n": len(raws),
                "avg": st.mean(raws),
                "median": st.median(raws),
                "win": sum(1 for x in raws if x > 0) / len(raws) * 100,
                "avg_adj": st.mean(adjs) if adjs else None,
                "win_adj": (sum(1 for x in adjs if x > 0) / len(adjs) * 100) if adjs else None,
            }
        else:
            summary[h] = None

    cards_html = ""
    for h in HZ:
        s = summary[h]
        if s is None:
            cards_html += (
                f'<div class="kpi"><div class="l">{h}</div><div class="v">データなし</div></div>'
            )
            continue
        cards_html += f"""
        <div class="kpi">
          <div class="l">{h}（N={s["n"]}）</div>
          <div class="v {"good" if s["avg"] >= 0 else "bad"}">{s["avg"]:+.2f}%</div>
          <div class="s">中央値 {s["median"]:+.2f}% ／ 勝率 {s["win"]:.0f}%</div>
          <div class="s" style="color:#7cc0ff;">対TOPIX {s["avg_adj"]:+.2f}%（勝率{s["win_adj"]:.0f}%）</div>
        </div>"""

    def latest_metric(r):
        for h in reversed(HZ):
            v = r["returns"].get(h)
            if v:
                return v["raw"]
        return -999

    ranked = sorted(results, key=latest_metric, reverse=True)

    rank_thead = "".join(f'<th style="text-align:right;">{h}</th>' for h in HZ)

    rank_rows = ""
    for i, r in enumerate(ranked, 1):
        cells = ""
        for h in HZ:
            v = r["returns"].get(h)
            if v is None:
                cells += '<td style="padding:6px 8px;text-align:right;color:#555;">経過待ち</td>'
            else:
                cells += (
                    f'<td style="padding:6px 8px;text-align:right;">{fmt_pct(v["raw"])}'
                    f'<br><span style="font-size:10px;color:#7cc0ff;">対TOPIX{fmt_pct(v["adjusted"])}</span></td>'
                )
        rank_rows += f"""
        <tr>
          <td style="padding:6px 8px;color:#999;text-align:right;">{i}</td>
          <td style="padding:6px 8px;color:#9fb0c8;font-size:11px;">{r["date"][4:6]}/{r["date"][6:8]}</td>
          <td style="padding:6px 8px;"><a href="https://kabutan.jp/stock/?code={r["code"]}" style="color:#4da3ff;font-weight:bold;text-decoration:none;" target="_blank">{r["code"]}</a></td>
          <td style="padding:6px 8px;">{r["company"]}</td>
          <td style="padding:6px 8px;font-size:11px;color:#9fb0c8;">{r["sector"]}</td>
          {cells}
        </tr>"""

    chart_data = [
        {"code": r["code"], "company": r["company"], "date": r["date"], "series": r["series"]}
        for r in results
    ]
    plain_data = [
        {
            "code": r["code"],
            "company": r["company"],
            "sector": r["sector"],
            "date": r["date"],
            "returns": {h: (r["returns"][h]["raw"] if r["returns"].get(h) else None) for h in HZ},
        }
        for r in results
    ]

    skipped_html = "".join(
        f"<li>{s['date']} {s['code']} {s['company']} — {s['reason']}</li>" for s in skipped
    )

    def corr_row(label, r, n):
        txt = f"r={r:+.3f}" if r is not None else "データ不足"
        return f'<tr><td style="padding:6px 10px;">{label}</td><td style="padding:6px 10px;text-align:right;">{txt}</td><td style="padding:6px 10px;text-align:right;color:#9fb0c8;">N={n}</td></tr>'

    def group_table(rows, title):
        if not rows:
            return f"<p style='color:#888;font-size:12px;'>{title}: データ不足</p>"
        body = "".join(
            f'<tr><td style="padding:5px 10px;">{r["label"]}</td>'
            f'<td style="padding:5px 10px;text-align:right;">N={r["n"]}</td>'
            f'<td style="padding:5px 10px;text-align:right;">{fmt_pct(r["avg"])}</td>'
            f'<td style="padding:5px 10px;text-align:right;color:#9fb0c8;">中央値{r["median"]:+.1f}%</td>'
            f'<td style="padding:5px 10px;text-align:right;color:#9fb0c8;">勝率{r["win"]:.0f}%</td></tr>'
            for r in rows
        )
        return f"""<div style="margin-bottom:14px;">
          <div style="font-size:12px;color:#9fb0c8;margin-bottom:4px;">{title}</div>
          <table style="width:100%;border-collapse:collapse;font-size:12px;">{body}</table>
        </div>"""

    corr_html = f"""
    <p class="lead">発表の種類・時価総額・自社株買い規模（発行済比率）・曜日とリターンの関係を検証（1週間リターン基準・結合N={corr["n_merged"]}）。</p>
    <table style="width:100%;border-collapse:collapse;font-size:12px;margin-bottom:16px;">
      <thead><tr style="color:#9fb0c8;"><th style="text-align:left;padding:6px 10px;">相関係数</th><th style="text-align:right;padding:6px 10px;">r</th><th></th></tr></thead>
      <tbody>
        {corr_row("自社株買い規模(発行済比率) vs 1週間リターン", corr["corr_ratio"], corr["n_ratio"])}
        {corr_row("時価総額 vs 1週間リターン", corr["corr_mcap"], corr["n_mcap"])}
      </tbody>
    </table>
    <p style="font-size:11px;color:#888;">|r|が0.3未満は実質無相関の目安。サンプルが少ない場合は参考程度に。</p>
    <div class="two">
      {group_table(corr["by_subtype"], "発表の種類別")}
      {group_table(corr["by_sector"], "業種別（N≥3のみ）")}
    </div>
    {group_table(corr["by_dow"], "曜日別")}
    """

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>自社株買い発表 株価反応 答え合わせ（週次）</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  :root{{--bg:#0f1419;--card:#1a2230;--card2:#202b3d;--line:#2c3a52;--txt:#e6edf6;--sub:#9fb0c8;
    --accent:#4da3ff;--green:#3ecf8e;--red:#ff6b6b;--gold:#ffcc66}}
  *{{box-sizing:border-box}}
  body{{margin:0;background:linear-gradient(160deg,#0c1016,#121a26);color:var(--txt);
    font-family:"Segoe UI","Hiragino Kaku Gothic ProN","Meiryo",sans-serif;line-height:1.7}}
  .wrap{{max-width:1200px;margin:0 auto;padding:28px 20px 80px}}
  a{{color:var(--accent);text-decoration:none}}
  h1{{font-size:1.9rem;margin:.1em 0 .3em}}
  .lead{{color:var(--sub);font-size:.95rem}}
  h2{{font-size:1.25rem;margin:34px 0 14px;padding-left:12px;border-left:4px solid var(--accent)}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}}
  .kpi{{background:var(--card2);border:1px solid var(--line);border-radius:12px;padding:14px 16px}}
  .kpi .l{{font-size:.8rem;color:var(--sub)}}
  .kpi .v{{font-size:1.6rem;font-weight:700;margin-top:2px}}
  .kpi .v.good{{color:var(--green)}} .kpi .v.bad{{color:var(--red)}}
  .kpi .s{{font-size:.72rem;color:var(--sub);margin-top:2px}}
  .chartbox{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;margin-bottom:16px}}
  .chwrap{{position:relative;height:280px}}
  .two{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
  @media(max-width:760px){{.two{{grid-template-columns:1fr}}}}
  table{{width:100%;border-collapse:collapse;font-size:12px}}
  thead th{{background:#1a2230;color:var(--sub);font-size:10px;padding:8px;text-align:left;position:sticky;top:0}}
  tbody tr:nth-child(even){{background:#161e2c}}
  .minigrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:10px}}
  .minicard{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 10px}}
  .minicard .t{{font-size:11px;color:var(--sub);margin-bottom:4px}}
  .minicard .t b{{color:var(--txt)}}
  .miniwrap{{height:110px}}
  details summary{{cursor:pointer;color:var(--gold);font-size:12px}}
  .note{{font-size:.78rem;color:var(--sub);background:rgba(255,204,102,.06);border:1px solid #3a3724;
    border-radius:10px;padding:12px 16px;margin-top:24px}}
</style>
</head>
<body>
<div class="wrap">
  <h1>🔔 新規自社株買い発表 株価反応・答え合わせ</h1>
  <p class="lead">週次自動更新（{week_disp} 時点）。対象: ir_digest の🔔新規発表検知・{len(results)}件（データ取得不可 {len(skipped)}件除く）。
    <b>IR発表は引け後が多いため、基準日=発表日の翌営業日の終値</b>。各ホライズンは基準日からの暦日ベースでその日以降最初の取引日の終値。
    「対TOPIX」は同期間のTOPIX（連動ETF 1306.T で代替）騰落率を差し引いた超過リターン。</p>

  <h2>① 集計結果（平均・中央値・勝率）</h2>
  <div class="grid">{cards_html}</div>

  <h2>② ホライズン別 平均リターン（生 vs 対TOPIX）</h2>
  <div class="chartbox"><div class="chwrap"><canvas id="summaryChart"></canvas></div></div>

  <h2>③ 個別ランキング（{len(results)}件・新しい経過済み期間の順）</h2>
  <div style="max-height:520px;overflow:auto;border:1px solid var(--line);border-radius:10px;">
  <table style="min-width:1100px;">
    <thead><tr><th>#</th><th>発表日</th><th>コード</th><th>会社</th><th>業種</th>
      {rank_thead}</tr></thead>
    <tbody>{rank_rows}</tbody>
  </table>
  </div>

  <h2>④ 個別チャート（基準日(翌営業日)=100として指数化、灰=TOPIX）</h2>
  <div class="minigrid" id="minigrid"></div>

  <h2>⑤ 値上がり／値下がりランキング（純粋な株価騰落・TOPIX比較なし）</h2>
  <p class="lead">その銘柄が実際に上がったか下がったかだけを見るランキング。期間ボタンで並び替え。</p>
  <div id="plainBtns" style="margin-bottom:10px;"></div>
  <div id="plainSummary" style="margin-bottom:10px;font-size:13px;color:#9fb0c8;"></div>
  <div style="max-height:600px;overflow:auto;border:1px solid var(--line);border-radius:10px;">
  <table>
    <thead><tr><th>#</th><th>発表日</th><th>コード</th><th>会社</th><th>業種</th>
      <th style="text-align:right;">騰落率</th></tr></thead>
    <tbody id="plainRows"></tbody>
  </table>
  </div>

  <h2>⑥ 何が効くか：相関・グループ分析</h2>
  {corr_html}

  <details style="margin-top:20px;">
    <summary>データ取得不可・除外 {len(skipped)}件（クリックで展開）</summary>
    <ul style="font-size:12px;color:#9fb0c8;">{skipped_html}</ul>
  </details>

  <p class="note">⚠️ TOPIX指数そのものはyfinanceで直接取得できないため、連動性の高いETF「1306.T」で代替しています。
    基準日を発表日の翌営業日にしたことで、発表当日の初動は測定に含みません＝より保守的・現実的な数値です。
    サンプル数が少ないホライズン・銘柄・グループが多く含まれます。過去の平均的な反応であり将来を保証しません。
    新規上場のアルファベット入り証券コードはyfinance非対応のため集計から除外しています。
    本レポートは公開情報の機械的集計であり投資助言ではありません。毎週自動更新されます。</p>
</div>

<script>
const grid='#2c3a52', sub='#9fb0c8';
Chart.defaults.color=sub; Chart.defaults.font.family='"Segoe UI","Meiryo",sans-serif';

const horizons = {json.dumps(HZ, ensure_ascii=False)};
const summary = {json.dumps(summary, ensure_ascii=False)};
new Chart(document.getElementById('summaryChart'), {{
  type: 'bar',
  data: {{ labels: horizons, datasets: [
    {{label:'平均リターン(生)', data: horizons.map(h=>summary[h]?summary[h].avg:null), backgroundColor:'rgba(77,163,255,.6)'}},
    {{label:'対TOPIX 超過リターン', data: horizons.map(h=>summary[h]?summary[h].avg_adj:null), backgroundColor:'rgba(62,207,142,.6)'}},
  ]}},
  options: {{responsive:true,maintainAspectRatio:false,
    plugins:{{legend:{{labels:{{boxWidth:12}}}}}},
    scales:{{x:{{grid:{{color:grid}}}},y:{{grid:{{color:grid}},title:{{display:true,text:'%'}}}}}}}}
}});

const chartData = {json.dumps(chart_data, ensure_ascii=False)};
const gridEl = document.getElementById('minigrid');
chartData.forEach((c, i) => {{
  const card = document.createElement('div'); card.className='minicard';
  const dstr = c.date.slice(4,6)+'/'+c.date.slice(6,8);
  card.innerHTML = `<div class="t"><b>${{c.code}}</b> ${{c.company}} <span style="color:#666;">(${{dstr}})</span></div>
    <div class="miniwrap"><canvas id="mc${{i}}"></canvas></div>`;
  gridEl.appendChild(card);
  const labels = c.series.map(p => p.date.slice(5));
  new Chart(document.getElementById('mc'+i), {{
    type:'line',
    data:{{labels, datasets:[
      {{label:'株価', data:c.series.map(p=>p.stock_idx), borderColor:'#4da3ff', borderWidth:1.5, pointRadius:0, tension:.2}},
      {{label:'TOPIX', data:c.series.map(p=>p.topix_idx), borderColor:'#666', borderWidth:1, pointRadius:0, tension:.2, borderDash:[3,2]}},
    ]}},
    options:{{responsive:true,maintainAspectRatio:false,animation:false,
      plugins:{{legend:{{display:false}}}},
      scales:{{x:{{display:false}},y:{{grid:{{color:'#22304588'}},ticks:{{font:{{size:9}}}}}}}}}}
  }});
}});

const plainData = {json.dumps(plain_data, ensure_ascii=False)};
let plainHorizon = '1ヶ月';
function renderPlainRanking() {{
  const rows = plainData.filter(r => r.returns[plainHorizon] !== null && r.returns[plainHorizon] !== undefined)
    .slice().sort((a, b) => b.returns[plainHorizon] - a.returns[plainHorizon]);
  const up = rows.filter(r => r.returns[plainHorizon] >= 0).length;
  const down = rows.length - up;
  document.getElementById('plainSummary').innerHTML =
    `${{plainHorizon}}後: 集計対象 <b>${{rows.length}}</b>件 ／ `
    + `<span style="color:#3ecf8e;">上昇 ${{up}}件（${{rows.length? (up/rows.length*100).toFixed(0):0}}%）</span> ／ `
    + `<span style="color:#ff6b6b;">下落 ${{down}}件（${{rows.length? (down/rows.length*100).toFixed(0):0}}%）</span>`;
  const tbody = document.getElementById('plainRows');
  tbody.innerHTML = rows.map((r, i) => {{
    const v = r.returns[plainHorizon];
    const color = v >= 0 ? '#3ecf8e' : '#ff6b6b';
    const dstr = r.date.slice(4,6)+'/'+r.date.slice(6,8);
    return `<tr>
      <td style="padding:6px 8px;color:#999;text-align:right;">${{i+1}}</td>
      <td style="padding:6px 8px;color:#9fb0c8;font-size:11px;">${{dstr}}</td>
      <td style="padding:6px 8px;"><a href="https://kabutan.jp/stock/?code=${{r.code}}" style="color:#4da3ff;font-weight:bold;" target="_blank">${{r.code}}</a></td>
      <td style="padding:6px 8px;">${{r.company}}</td>
      <td style="padding:6px 8px;font-size:11px;color:#9fb0c8;">${{r.sector}}</td>
      <td style="padding:6px 8px;text-align:right;color:${{color}};font-weight:bold;">${{v>=0?'+':''}}${{v.toFixed(1)}}%</td>
    </tr>`;
  }}).join('');
}}
const btnWrap = document.getElementById('plainBtns');
horizons.forEach(h => {{
  const b = document.createElement('button');
  b.textContent = h;
  b.style.cssText = 'background:#202b3d;color:#9fb0c8;border:1px solid #2c3a52;border-radius:8px;'
    + 'padding:6px 14px;margin:0 6px 6px 0;cursor:pointer;font-size:12px;';
  b.onclick = () => {{
    plainHorizon = h;
    [...btnWrap.children].forEach(c => {{ c.style.background='#202b3d'; c.style.color='#9fb0c8'; }});
    b.style.background = '#2a4a6a'; b.style.color = '#e6edf6';
    renderPlainRanking();
  }};
  if (h === plainHorizon) {{ b.style.background = '#2a4a6a'; b.style.color = '#e6edf6'; }}
  btnWrap.appendChild(b);
}});
renderPlainRanking();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description="自社株買い答え合わせ（週次）")
    p.add_argument("--no-send", action="store_true")
    args = p.parse_args()

    load_dotenv(ROOT_DIR / "config.env")
    output_dir = SCRIPT_DIR / os.getenv("BACKTEST_OUTPUT_DIR", "output")
    output_dir.mkdir(parents=True, exist_ok=True)
    start_date = os.getenv("BUYBACK_BACKTEST_START_DATE", "20260602")

    events = load_events(start_date)
    logger.info("イベント抽出: %d 件（%s〜今日）", len(events), start_date)

    results, skipped = compute_returns(events, start_date)
    logger.info("株価取得: 成功 %d / スキップ %d", len(results), len(skipped))

    logger.info("追加ファクター取得中（時価総額・自社株買い規模）...")
    factors = enrich_factors(events)
    corr = build_correlation_analysis(results, factors)

    week_disp = datetime.now().strftime("%Y-%m-%d")
    html = build_html(results, skipped, corr, week_disp)

    out_path = output_dir / "buyback_backtest.html"
    out_path.write_text(html, encoding="utf-8")
    logger.info("HTML保存: %s", out_path)

    if args.no_send:
        logger.info("--no-send 指定のため送信しません。")
        return 0

    gmail_address = os.getenv("GMAIL_ADDRESS", "")
    gmail_app_password = os.getenv("GMAIL_APP_PASSWORD", "")
    recipient = os.getenv("RECIPIENT_EMAIL", "")
    if not (gmail_address and gmail_app_password and recipient):
        logger.error("Gmail設定が不足。送信をスキップします。")
        return 1

    n1w = sum(1 for r in results if r["returns"].get("1週間"))
    subject = (
        f"[自社株買い答え合わせ] 週次レビュー {week_disp}（{len(results)}件・1週間集計{n1w}件）"
    )
    try:
        email_sender.send_html(html, subject, gmail_address, gmail_app_password, recipient)
    except Exception as e:
        logger.error("メール送信失敗: %s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
