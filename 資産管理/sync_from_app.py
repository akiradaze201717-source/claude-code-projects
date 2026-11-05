"""「資産手帳」アプリ(Claude Artifact)からの入力値を 残高入力.xlsx に反映する橋渡しスクリプト。

運用の流れ:
  1. ユーザーがスマホの「資産手帳」アプリで残高を入力・保存する
     （アプリのデータベースに直接保存される。この時点ではまだ確定しない）
  2. ユーザーがClaudeに「確定して」と伝える
  3. Claudeが Artifact の read_db でアプリの入力値(口座名 -> 金額)を取得し、
     一時JSONファイルとして保存した上でこのスクリプトを呼び出す
  4. このスクリプトは `python main.py remind` 実行後（GMO自動値が入った状態）の
     残高入力.xlsx に対し、空欄になっている「今回残高」列をアプリの入力値で埋める
  5. Claudeが `python main.py commit` を実行し、確定・記録・ダッシュボード生成・
     Vault書き戻しまでを行う
  6. Claudeが最新の純資産・内訳をアプリのDBにも write_db で反映し、
     アプリ側の「今回残高」欄をクリアする（次週分の入力に備える）

使い方:
  python main.py remind          # 先にGMO自動値込みのテンプレートを用意する
  python sync_from_app.py <values.json>
  python main.py commit

<values.json> の形式（口座名をキーにする。balances/accounts.py の Account.name と一致させること）:
  {"SBI証券(国内株式)": 250000, "PayPay": 1200, ...}
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from dotenv import load_dotenv

# ASSET_SYNC_DIR等をos.environに反映してからtemplate_builderをimportする必要がある
# （PENDING_DIR/TEMPLATE_PATHはモジュール読み込み時に一度だけ解決されるため）。
load_dotenv(Path(__file__).parent / "config.env")

from balances.accounts import load_accounts
from balances.template_builder import fill_auto_values, find_latest_pending_template


def main() -> int:
    if len(sys.argv) != 2:
        print("使い方: python sync_from_app.py <values.json>")
        return 1

    values_path = Path(sys.argv[1])
    values_by_name = json.loads(values_path.read_text(encoding="utf-8"))

    template_path = find_latest_pending_template()
    if template_path is None:
        print("残高入力.xlsx が見つかりません。先に `python main.py remind` を実行してください。")
        return 1

    accounts = load_accounts()
    name_to_id = {a.name: a.id for a in accounts}

    unknown = [name for name in values_by_name if name not in name_to_id]
    if unknown:
        print(f"警告: 口座マスタに無い名前はスキップします: {unknown}")

    values_by_id = {
        name_to_id[name]: float(value)
        for name, value in values_by_name.items()
        if name in name_to_id and value is not None
    }

    filled = fill_auto_values(template_path, values_by_id, accounts, note_prefix="アプリからの入力")
    print(f"{filled}件をアプリの入力値で反映しました: {template_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
