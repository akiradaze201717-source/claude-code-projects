"""これから自社株買いする銘柄（新規発表）の日次まとめ。

TDnetのその日の開示から、自社株買いの「新規発表」（取得枠の新規設定／
取得に係る事項の決定／立会外買付ToSTNeT-3の開始）だけを抽出する。
取得状況（進捗）・取得終了・消却・株式分割・優待・TOB等は対象外。
あわせて対象企業向けのAI調査プロンプトを生成する。

使い方:
  python buyback_daily.py                    # 本日の開示を処理して送信
  python buyback_daily.py --date 20260602     # 日付指定
  python buyback_daily.py --date 20260602 --no-send   # 送信せずHTMLのみ生成
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent  # .../ir_digest/daily
ROOT_DIR = SCRIPT_DIR.parent  # .../ir_digest （共有リソース置き場）
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(ROOT_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import buyback_report_html
import email_sender  # ROOT_DIR直下の共有モジュール
import research_prompt
import sector_lookup
import tdnet_fetcher
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("buyback_daily")

ARCHIVE_PATH = ROOT_DIR / "buyback_events_archive.json"  # backtestと共有する恒久イベント台帳


def parse_args():
    p = argparse.ArgumentParser(description="自社株買い・資本政策の日次まとめ")
    p.add_argument("--date", help="対象日 YYYYMMDD（既定: 本日）")
    p.add_argument("--no-send", action="store_true", help="メール送信せずHTMLのみ生成")
    return p.parse_args()


def load_config() -> dict:
    load_dotenv(ROOT_DIR / "config.env")
    return {
        "gmail_address": os.getenv("GMAIL_ADDRESS", ""),
        "gmail_app_password": os.getenv("GMAIL_APP_PASSWORD", ""),
        "recipient": os.getenv("RECIPIENT_EMAIL", ""),
        "output_dir": os.getenv("DAILY_OUTPUT_DIR", "output"),
        "research_dir": os.getenv("RESEARCH_DIR", "../../個別銘柄調査"),
        "research_exclude_sectors": [
            s.strip() for s in os.getenv("RESEARCH_EXCLUDE_SECTORS", "").split(",") if s.strip()
        ],
    }


def _update_archive(disclosures, date_yyyymmdd: str) -> None:
    """本日発見した🔔新規発表を、backtestと共有する恒久台帳へマージ保存する。

    これによりbacktest側はHTMLを再スキャンせずアーカイブJSONを読むだけでよく、
    daily/backtestを別フォルダに分けても互いのHTML出力に依存しない。
    """
    archive: dict[tuple, dict] = {}
    if ARCHIVE_PATH.exists():
        for e in json.loads(ARCHIVE_PATH.read_text(encoding="utf-8")):
            archive[(e["date"], e["code"])] = e

    for d in disclosures:
        if tdnet_fetcher.is_forthcoming_buyback(d.title):
            archive[(date_yyyymmdd, d.code)] = {
                "date": date_yyyymmdd,
                "code": d.code,
                "company": d.company,
                "sector": d.sector,
                "title": d.title,
                "pdf_url": d.pdf_url,
            }

    merged = sorted(archive.values(), key=lambda e: (e["date"], e["code"]))
    ARCHIVE_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    args = parse_args()
    cfg = load_config()

    date_yyyymmdd = args.date or datetime.now().strftime("%Y%m%d")
    date_disp = f"{date_yyyymmdd[:4]}-{date_yyyymmdd[4:6]}-{date_yyyymmdd[6:8]}"
    logger.info("対象日: %s", date_disp)

    # 1) 開示一覧取得
    disclosures, source = tdnet_fetcher.fetch_disclosures(date_yyyymmdd)
    if not disclosures:
        logger.warning("開示が0件でした。日付（営業日か）をご確認ください。")

    # 2) 業種を補完
    sector_map = sector_lookup.get_sector_map(SCRIPT_DIR / "cache")
    if sector_map:
        for d in disclosures:
            d.sector = sector_map.get(d.code, "")

    forthcoming = [d for d in disclosures if tdnet_fetcher.is_forthcoming_buyback(d.title)]
    logger.info("新規自社株買い発表: %d 件", len(forthcoming))

    # 2.5) backtest共有の恒久台帳へマージ保存（HTML経由の依存を無くす）
    _update_archive(disclosures, date_yyyymmdd)

    # 3) 調査プロンプトを生成・保存（LLM不使用＝費用ゼロ）
    research_dir = (
        (SCRIPT_DIR / cfg["research_dir"])
        if not os.path.isabs(cfg["research_dir"])
        else Path(cfg["research_dir"])
    )
    research_dir = research_dir.resolve()
    prompt_path, research_n, research_prompt_text = research_prompt.write(
        disclosures,
        research_dir,
        date_yyyymmdd,
        date_disp,
        exclude_sectors=cfg["research_exclude_sectors"],
    )
    if prompt_path:
        logger.info("調査プロンプト生成: %s（対象 %d 社）", prompt_path, research_n)

    # 4) HTML生成
    html = buyback_report_html.build_report(date_disp, disclosures, research_prompt_text)
    out_dir = (
        (SCRIPT_DIR / cfg["output_dir"])
        if not os.path.isabs(cfg["output_dir"])
        else Path(cfg["output_dir"])
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"buyback_daily_{date_yyyymmdd}.html"
    out_path.write_text(html, encoding="utf-8")
    logger.info("HTML保存: %s", out_path)

    # 5) 送信
    if args.no_send:
        logger.info("--no-send 指定のため送信しません。")
    else:
        if not (cfg["gmail_address"] and cfg["gmail_app_password"] and cfg["recipient"]):
            logger.error("Gmail設定が不足。config.env を確認してください。送信をスキップします。")
        else:
            subject = f"[自社株買い] {date_disp} 新規発表{len(forthcoming)}件"
            try:
                email_sender.send_html(
                    html,
                    subject,
                    cfg["gmail_address"],
                    cfg["gmail_app_password"],
                    cfg["recipient"],
                )
            except Exception as e:
                logger.error("メール送信失敗: %s", e)
                return 1

    if forthcoming:
        print("\n===== これから自社株買い（新規発表） =====")
        for d in sorted(forthcoming, key=lambda x: x.time):
            print(f"  {d.code} {d.company[:16]:16s} {d.sector or '—':8s} | {d.title[:46]}")

    print(f"\nHTML: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
