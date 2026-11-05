"""週次の手動残高入力用Excelファイル(残高入力.xlsx)の生成・読み込み。

常に同じファイル名を使い回す方式。ユーザーはこのファイルをExcel等で直接開いて
「今回残高」列に入力する（Claude/チャット経由ではなく、資産管理プロジェクトのファイルの中で
完結させたいという要望に対応）。

環境変数 ASSET_SYNC_DIR（config.env）が設定されていれば、そちらをファイルの置き場所として使う。
個人用OneDrive等の同期フォルダを指定すればスマホからExcelアプリで直接編集できる。
未設定時は従来通りローカルの data/pending/ を使う。

対象日はファイル名ではなくシート内のセル(A1ラベル+B1値)に埋め込む。
commit確定後は当該回の内容を archive/ へ日付付きでコピー保存し、
「今回残高」列だけを空にして次回入力に備える。
"""

import logging
import os
from pathlib import Path

import openpyxl
from balances.accounts import AUTO_SOURCES, SOURCE_AUTO_GMO, SOURCE_AUTO_GMO_CRYPTO, Account
from balances.ledger import get_previous_balance
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

log = logging.getLogger(__name__)

_LOCAL_PENDING_DIR = Path(__file__).parent.parent / "data" / "pending"
PENDING_DIR = (
    Path(os.environ["ASSET_SYNC_DIR"]) if os.environ.get("ASSET_SYNC_DIR") else _LOCAL_PENDING_DIR
)
TEMPLATE_PATH = PENDING_DIR / "残高入力.xlsx"

SHEET_TITLE = "残高入力"
HEADERS = ["口座名", "区分", "前回残高", "今回残高", "メモ"]
TYPE_DISPLAY = {"asset": "資産", "liability": "負債"}

DATE_LABEL_CELL = "A1"
DATE_VALUE_CELL = "B1"
HEADER_ROW = 3
DATA_START_ROW = 4
COL_NAME, COL_TYPE, COL_PREV, COL_CURRENT, COL_NOTE = 1, 2, 3, 4, 5

NUMBER_FORMAT = "#,##0"
INPUT_FILL = PatternFill(start_color="FFF9E5B0", end_color="FFF9E5B0", fill_type="solid")
COLUMN_WIDTHS = [24, 8, 13, 14, 34]


def to_dashed_date(raw_date: str) -> str:
    """ "20260831" -> "2026-08-31"（残高台帳の日付表記と揃える）。"""
    return f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"


def find_latest_pending_template() -> Path | None:
    """確定待ちの残高入力ファイルを返す（無ければ None）。ファイル名は常に固定。"""
    return TEMPLATE_PATH if TEMPLATE_PATH.exists() else None


def _read_existing_inputs(path: Path) -> dict[str, float]:
    """既存ファイルから 口座名 -> 入力済みの今回残高 の辞書を返す（未確定分の引き継ぎ用）。"""
    if not path.exists():
        return {}
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    inputs: dict[str, float] = {}
    for row_idx in range(DATA_START_ROW, ws.max_row + 1):
        name = ws.cell(row=row_idx, column=COL_NAME).value
        current = ws.cell(row=row_idx, column=COL_CURRENT).value
        if name and current not in (None, ""):
            try:
                inputs[str(name)] = float(current)
            except (TypeError, ValueError):
                continue
    return inputs


def build_weekly_template(
    raw_date: str,
    accounts: list[Account],
    gmo_jpy_balance: float | None,
    gmo_crypto_balance: float | None,
) -> Path:
    """週次残高入力用Excelファイルを生成（既存ファイルは上書き）する。raw_date は YYYYMMDD（8桁）。

    - GMO関連口座(auto_gmo / auto_gmo_crypto)は自動取得値を「今回残高」に入れて確定済み扱いにする
      （取得失敗時は空欄にし note へ「自動取得失敗」を記す＝手動記入にフォールバック）。
    - 他口座は「前回残高」を参考値として表示し、「今回残高」は空欄にする。
    - 既存ファイルに入力途中の値がある場合、口座名で突き合わせて引き継ぐ
      （remindを複数回実行しても入力中の値が消えないように）。
    """
    date_str = to_dashed_date(raw_date)
    carried_inputs = _read_existing_inputs(TEMPLATE_PATH)

    auto_values = {
        SOURCE_AUTO_GMO: gmo_jpy_balance,
        SOURCE_AUTO_GMO_CRYPTO: gmo_crypto_balance,
    }

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = SHEET_TITLE

    ws[DATE_LABEL_CELL] = "対象日"
    ws[DATE_LABEL_CELL].font = Font(bold=True)
    ws[DATE_VALUE_CELL] = date_str

    for col_idx, header in enumerate(HEADERS, start=1):
        cell = ws.cell(row=HEADER_ROW, column=col_idx, value=header)
        cell.font = Font(bold=True)

    row_idx = DATA_START_ROW
    for account in accounts:
        prev = get_previous_balance(account.id, before_date=date_str)

        current_value = None
        note = ""

        if account.source in AUTO_SOURCES:
            auto_value = auto_values.get(account.source)
            if auto_value is not None:
                current_value = auto_value
                note = "自動取得値(参考・修正可)"
            else:
                note = "自動取得失敗 — 手動で入力してください"
                current_value = carried_inputs.get(account.name)
        else:
            current_value = carried_inputs.get(account.name)
            if account.type == "liability":
                note = "請求額(正の数)で入力"

        ws.cell(row=row_idx, column=COL_NAME, value=account.name)
        ws.cell(row=row_idx, column=COL_TYPE, value=TYPE_DISPLAY.get(account.type, account.type))
        prev_cell = ws.cell(row=row_idx, column=COL_PREV, value=prev)
        prev_cell.number_format = NUMBER_FORMAT
        current_cell = ws.cell(row=row_idx, column=COL_CURRENT, value=current_value)
        current_cell.number_format = NUMBER_FORMAT
        current_cell.fill = INPUT_FILL
        ws.cell(row=row_idx, column=COL_NOTE, value=note)
        row_idx += 1

    for i, width in enumerate(COLUMN_WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.freeze_panes = f"A{DATA_START_ROW}"

    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    wb.save(TEMPLATE_PATH)
    log.info("週次入力ファイル(Excel)生成: %s", TEMPLATE_PATH)
    return TEMPLATE_PATH


def read_target_date(path: Path = TEMPLATE_PATH) -> str:
    """シートの対象日セル(B1)から日付文字列(YYYY-MM-DD)を読む。"""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    value = ws[DATE_VALUE_CELL].value
    if value in (None, ""):
        raise ValueError(f"対象日セル({DATE_VALUE_CELL})が空です: {path}")
    return str(value)


def _iter_data_rows(ws):
    for row_idx in range(DATA_START_ROW, ws.max_row + 1):
        name = ws.cell(row=row_idx, column=COL_NAME).value
        if not name:
            continue
        yield (
            row_idx,
            str(name),
            ws.cell(row=row_idx, column=COL_CURRENT).value,
        )


def fill_auto_values(
    path: Path,
    auto_values: dict[str, float],
    accounts: list[Account],
    note_prefix: str = "自動取得値(CSV)",
) -> int:
    """「今回残高」が空欄の行のうち、account_id が auto_values に含まれるものを埋める。

    既に値が入っている行（ユーザーが手動入力済み含む）は上書きしない。
    カード明細CSVから抽出した請求額合計を反映する用途で使う。埋めた件数を返す。
    """
    if not auto_values:
        return 0

    name_to_id = {a.name: a.id for a in accounts}
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    filled = 0
    for row_idx, name, current in _iter_data_rows(ws):
        if current not in (None, ""):
            continue
        account_id = name_to_id.get(name)
        if account_id is None:
            continue
        value = auto_values.get(account_id)
        if value is None:
            continue
        cell = ws.cell(row=row_idx, column=COL_CURRENT, value=value)
        cell.number_format = NUMBER_FORMAT
        ws.cell(row=row_idx, column=COL_NOTE, value=f"{note_prefix}:{value:.0f}(参考・修正可)")
        filled += 1

    if filled:
        wb.save(path)
        log.info("テンプレートに自動値を%d件反映: %s", filled, path)
    return filled


def missing_manual_accounts(template_path: Path, accounts: list[Account]) -> list[str]:
    """「今回残高」が未入力の口座名一覧を返す。"""
    wb = openpyxl.load_workbook(template_path, data_only=True)
    ws = wb.active
    return [name for _idx, name, current in _iter_data_rows(ws) if current in (None, "")]


def read_template_entries(template_path: Path, accounts: list[Account]) -> list[dict]:
    """入力済みファイルを読み、台帳追記用のエントリ配列を返す（今回残高が空欄の行は除外）。

    口座名で口座マスタと突き合わせ、口座マスタの source（auto_gmo / auto_card_csv / manual 等）を
    そのまま台帳に記録する（自動取得値をユーザーが手で修正した場合でも由来が分かるようにする）。
    """
    by_name = {a.name: a for a in accounts}
    wb = openpyxl.load_workbook(template_path, data_only=True)
    ws = wb.active

    entries = []
    for row_idx, name, current in _iter_data_rows(ws):
        if current in (None, ""):
            continue
        try:
            balance = float(current)
        except (TypeError, ValueError):
            log.warning(
                "残高が数値として解釈できません: 口座=%s value=%r — スキップ", name, current
            )
            continue
        account = by_name.get(name)
        if account is None:
            log.warning("口座マスタに無い口座名です: %s — スキップ", name)
            continue
        note = ws.cell(row=row_idx, column=COL_NOTE).value
        entries.append(
            {
                "account_id": account.id,
                "balance": balance,
                "source": account.source,
                "note": str(note) if note else "",
            }
        )
    return entries


def archive_and_reset(template_path: Path, date_str: str) -> Path:
    """確定内容を archive/ へ日付付きでコピー保存し、「今回残高」列を空にして
    ライブファイル(残高入力.xlsx)を次回入力用にリセットする。archiveされたファイルのパスを返す。

    archive先は template_path と同じ親ディレクトリ配下（本番では PENDING_DIR/archive）とする
    （固定のARCHIVE_DIR定数を参照すると、テスト等でtemplate_pathを差し替えた際に
    実際のファイルと保存先ディレクトリが食い違うため）。
    """
    archive_dir = template_path.parent / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    raw_date = date_str.replace("-", "")
    archived_path = archive_dir / f"残高入力_{raw_date}.xlsx"

    wb = openpyxl.load_workbook(template_path)
    wb.save(archived_path)

    ws = wb.active
    for row_idx in range(DATA_START_ROW, ws.max_row + 1):
        if ws.cell(row=row_idx, column=COL_NAME).value:
            ws.cell(row=row_idx, column=COL_CURRENT).value = None
    wb.save(template_path)

    log.info("確定内容をarchiveへ保存し、入力欄をリセット: %s", archived_path)
    return archived_path
