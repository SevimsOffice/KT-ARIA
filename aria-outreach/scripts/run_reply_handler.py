"""
ARIA Reply Handler — runs every 2 hours via GitHub Actions.
Checks Instantly.ai for new replies, classifies with Claude,
and alerts Sevim on Telegram for hot/warm leads.
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
from src.replies.reply_fetcher import ReplyFetcher
from src.replies.classifier import ReplyClassifier
from src.notifications.telegram import TelegramNotifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("aria.replies")


def run(dry_run: bool = False):
    logger.info("=== ARIA Reply Handler ===")

    cfg = get_config()

    if not cfg.reply_handling_enabled:
        logger.info("Reply handling is disabled (REPLY_HANDLING_ENABLED=false) — skipping run.")
        return {"processed": 0, "skipped": True}

    sheets     = SheetsClient(cfg.google_service_account_json, cfg.google_sheet_id)
    sheets.connect()
    instantly  = InstantlyClient(cfg.instantly_api_key, cfg.instantly_campaign_id)
    fetcher    = ReplyFetcher(instantly, sheets)
    classifier = ReplyClassifier(cfg.anthropic_api_key)
    telegram   = TelegramNotifier(cfg.telegram_bot_token, cfg.telegram_chat_id)

    # Fetch new replies
    replies = fetcher.fetch_new_replies()
    if not replies:
        logger.info("No new replies")
        return {"processed": 0}

    hot = 0
    warm = 0
    for reply in replies:
        from_email  = reply.get("from_email", "")
        body        = reply.get("body", "")
        lead_email  = reply.get("lead_email", from_email)

        logger.info(f"Classifying reply from: {from_email}")
        result = classifier.classify(body, from_email)
        category  = result["category"]
        summary   = result["summary"]

        logger.info(f"  → {category}: {summary}")

        # Look up company details from sheet
        company_info = _find_company_by_email(sheets, lead_email)
        company_name = company_info.get("Company_Name", lead_email)
        sector       = company_info.get("Sector", "")
        osb          = company_info.get("OSB", "")
        domain       = company_info.get("Domain", "")
        contact_name = company_info.get("Contact_Name", "")

        if dry_run:
            logger.info(f"  [DRY RUN] Would update sheet + notify Telegram: {category}")
            continue

        # Update sheet
        if domain:
            sheets.update_status(domain, {
                "Reply_Category": category,
                "Reply_Date": __import__("datetime").date.today().isoformat(),
                "ARIA_Status": f"Replied_{category}",
                "Hot_Lead": "YES" if category == "HOT" else "",
            })

        # Telegram notifications
        if category == "HOT":
            hot += 1
            telegram.send_hot_lead_alert(
                company_name=company_name,
                sector=sector,
                osb=osb,
                reply_text=body,
                summary=summary,
                suggested_response=result.get("suggested_response", ""),
                domain=domain,
                contact_name=contact_name,
            )
        elif category == "WARM":
            warm += 1
            telegram.send_warm_lead_notice(company_name, summary)
        elif category == "UNSUBSCRIBE":
            if domain:
                sheets.update_status(domain, {"ARIA_Status": "Unsubscribed"})

    logger.info(f"Done: {hot} HOT, {warm} WARM, {len(replies)} total")
    return {"processed": len(replies), "hot": hot, "warm": warm}


def _find_company_by_email(sheets: SheetsClient, email: str) -> dict:
    """Find company record by email address."""
    records = sheets.get_all_records()
    for r in records:
        if r.get("Email", "").lower().strip() == email.lower().strip():
            return r
    return {}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ARIA Reply Handler")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
