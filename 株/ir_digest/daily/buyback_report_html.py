"""自社株買い・資本政策の日次HTMLレポート生成（ir_digestとは別ファイル・別メール）。

これから自社株買いをする（新規発表）銘柄のみに絞る。取得状況（進捗）・
取得終了・消却・分割・優待・TOBなどの広い資本政策一覧は扱わない。
"""

import html as _html

from tdnet_fetcher import Disclosure, is_forthcoming_buyback


def build_report(
    date_disp: str,
    disclosures: list[Disclosure],
    research_prompt_text: str = "",
) -> str:
    forthcoming_n = sum(1 for d in disclosures if is_forthcoming_buyback(d.title))

    forthcoming_box = _build_forthcoming_box(disclosures)
    research_box = _build_research_box(research_prompt_text)

    return f"""<!DOCTYPE html>
<html lang="ja">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="font-family:'Helvetica Neue',Arial,'Hiragino Sans','Yu Gothic',sans-serif;
    max-width:960px;margin:0 auto;padding:20px;color:#2c3e50;background:#fff;">
    <h1 style="border-bottom:3px solid #8e44ad;padding-bottom:10px;font-size:22px;">
        🔔 これから自社株買い　<span style="color:#8e44ad;">{date_disp}</span>
    </h1>
    <p style="color:#666;font-size:13px;margin:6px 0 20px;">
        新規自社株買い発表 <strong>{forthcoming_n}</strong> 件
    </p>

    {forthcoming_box}
    {research_box}

    <div style="margin-top:28px;padding:12px;background:#fff3cd;border-radius:6px;font-size:11px;color:#856404;">
      本レポートは公開情報（適時開示）の機械的な集計であり、投資助言ではありません。
      取得金額・株数の詳細はPDF本文に記載（これらの開示はXBRL未提供のため数値の自動抽出は不可）。
      投資判断はご自身の責任で行ってください。
    </div>
</body>
</html>"""


def _build_forthcoming_box(disclosures: list[Disclosure]) -> str:
    """これから自社株買いを行う新規発表だけを目立つ枠で表示。"""
    fc = [d for d in disclosures if is_forthcoming_buyback(d.title)]
    if not fc:
        return (
            '<div style="padding:10px 14px;background:#f6f6f6;border-radius:6px;'
            'color:#888;font-size:13px;">本日の新規発表はありませんでした。</div>'
        )
    fc.sort(key=lambda d: d.time)
    rows = ""
    for d in fc:
        kabutan = f"https://kabutan.jp/stock/?code={d.code}"
        pdf = f'<a href="{d.pdf_url}" style="color:#2980b9;">PDF</a>' if d.pdf_url else "—"
        rows += f"""
        <tr>
          <td style="padding:7px 9px;border-bottom:1px solid #f0d9b8;color:#999;font-size:11px;">{d.time}</td>
          <td style="padding:7px 9px;border-bottom:1px solid #f0d9b8;white-space:nowrap;">
            <a href="{kabutan}" style="color:#b9770e;font-weight:bold;text-decoration:none;">{d.code}</a></td>
          <td style="padding:7px 9px;border-bottom:1px solid #f0d9b8;font-weight:bold;">{d.company}</td>
          <td style="padding:7px 9px;border-bottom:1px solid #f0d9b8;font-size:11px;color:#777;">{d.sector or "—"}</td>
          <td style="padding:7px 9px;border-bottom:1px solid #f0d9b8;font-size:12px;color:#444;">{d.title}</td>
          <td style="padding:7px 9px;border-bottom:1px solid #f0d9b8;font-size:11px;">{pdf}</td>
        </tr>"""
    return f"""
    <div style="border:2px solid #e67e22;border-radius:8px;padding:8px 12px;background:#fff8ef;">
      <div style="font-weight:bold;color:#b9770e;font-size:14px;margin-bottom:4px;">
        🔔 これから自社株買いを行う銘柄（新規発表 {len(fc)} 件）
      </div>
      <p style="font-size:11px;color:#888;margin:0 0 6px;">
        取得枠の新規設定／取得に係る事項の決定／立会外買付(ToSTNeT-3) を抽出。
        進捗報告・取得終了・消却は除外。取得金額・株数はPDF本文参照。
      </p>
      <table style="width:100%;border-collapse:collapse;font-size:13px;">
        <thead><tr style="background:#fbe9d3;font-size:11px;">
          <th style="padding:6px 9px;text-align:left;">時刻</th>
          <th style="padding:6px 9px;text-align:left;">コード</th>
          <th style="padding:6px 9px;text-align:left;">会社</th>
          <th style="padding:6px 9px;text-align:left;">業種</th>
          <th style="padding:6px 9px;text-align:left;">タイトル</th>
          <th style="padding:6px 9px;text-align:left;">資料</th>
        </tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>"""


def _build_research_box(prompt_text: str) -> str:
    """自社株買い企業をAIに調査させる貼り付け用プロンプトを折りたたみで表示。"""
    if not prompt_text:
        return ""
    escaped = _html.escape(prompt_text)
    return f"""
    <details style="margin-top:18px;">
      <summary style="cursor:pointer;font-size:14px;color:#8e44ad;font-weight:bold;">
        🤖 この企業をAIに調査させるプロンプト（クリックで展開・コピー）
      </summary>
      <p style="font-size:11px;color:#888;margin:6px 0;">
        下のテキストをコピーしてClaudeに貼り付けると、既存の個別銘柄調査と同じ形式で
        各社のフルレポートHTMLが生成されます（ツールはプロンプト生成のみ・追加費用なし）。
        同じ内容は <code>個別銘柄調査\\_daily_prompt_*.md</code> にも保存されています。
      </p>
      <pre style="background:#0c121c;color:#cfe3ff;border:1px solid #2c3a52;border-radius:8px;
        padding:14px;font-size:12px;white-space:pre-wrap;overflow:auto;max-height:340px;">{escaped}</pre>
    </details>"""
