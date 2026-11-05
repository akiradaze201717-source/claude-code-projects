"""ログ設定ヘルパー — コンソールとファイルに同時出力する。"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).parent / "logs"
FMT = "%(asctime)s [%(levelname)s] %(message)s"
DATE_FMT = "%Y-%m-%d %H:%M:%S"


def setup_logger(log_filename: str) -> None:
    """ルートロガーにコンソールとローテーティングファイルハンドラを設定する。

    log_filename: logs/ 以下のファイル名（例: "dca.log"）
    ファイルは最大 1MB × 5世代保持。
    """
    LOG_DIR.mkdir(exist_ok=True)
    log_path = LOG_DIR / log_filename

    handlers: list[logging.Handler] = [
        logging.StreamHandler(),  # コンソール
        RotatingFileHandler(
            log_path,
            maxBytes=1_000_000,  # 1MB
            backupCount=5,
            encoding="utf-8",
        ),
    ]

    logging.basicConfig(
        level=logging.INFO,
        format=FMT,
        datefmt=DATE_FMT,
        handlers=handlers,
    )
