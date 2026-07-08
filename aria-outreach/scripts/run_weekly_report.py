"""
ARIA Weekly Report — runs every Sunday at 8 AM Turkey time.
Compiles stats from Google Sheets and sends intelligence summary to Telegram.
"""

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from src.config import get_config
from src.database.sheets_client import SheetsClient
from src.outreach.instantly_client import InstantlyClient
from src.notifications.telegram import TelegramNotifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s")
logger = logging.getLogger("aria.weekly")


def run():
    logger.info("=== ARIA Weekly Report ===")
    cfg = get_config()

    sheets   = SheetsClient(cfg.google_service_account_json, cfg.google_sheet_id)
    sheets.connect()
    telegram = TelegramNotifier(cfg.telegram_bot_token, cfg.telegram_chat_id)

    stats = sheets.get_weekly_stats()
    logger.info(f"Stats: {stats}")
    telegram.send_weekly_report(stats)
    logger.info("Weekly report sent")


if __name__ == "__main__":
    run()
