"""
ARIA Resend — Sheet'teki mevcut contactları Instantly'ye gönderir.

Kimler gönderilir:
  - Google Sheet'te ARIA_Status = "Added_to_Instantly" olan AMA
    Instantly'de gerçekte olmayan contactlar (pipeline hata verdiğinde
    sheet yazılıp Instantly'ye eklenememişti)
  - Reply almamış, unsubscribe olmamış contactlar

Kimler atlanır:
  - Replied_* veya Unsubscribed statuslü contactlar
  - Email adresi olmayanlar

Kullanım:
  python scripts/run_resend_from_sheet.py               # günlük limit
  python scripts/run_resend_from_sheet.py --limit 10    # max 10 contact
  python scripts/run_resend_from_sheet.py --dry-run     # göster, gönderme
"""

import argparse
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from src.config import get_config
from src.database.sheets_client import SheetsClient
from src.outreach.instantly_client import InstantlyClient
from src.outreach.email_composer import _fallback_personalized_line
from src.notifications.telegram import TelegramNotifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("aria.resend")

SKIP_STATUSES = {"Replied_HOT", "Replied_WARM", "Replied_COLD", "Unsubscribed"}


def run(dry_run: bool = False, limit: int = 30):
    logger.info(f"=== ARIA Resend from Sheet {'(DRY RUN) ' if dry_run else ''}— limit={limit} ===")

    cfg = get_config()
    sheets   = SheetsClient(cfg.google_service_account_json, cfg.google_sheet_id)
    sheets.connect()
    instantly = InstantlyClient(cfg.instantly_api_key, cfg.instantly_campaign_id)
    telegram  = TelegramNotifier(cfg.telegram_bot_token, cfg.telegram_chat_id)

    records = sheets.get_all_records()
    logger.info(f"Sheet'te toplam {len(records)} kayıt")

    # Filter: has email, not replied/unsubscribed, not guessed (domain protection)
    candidates = [
        r for r in records
        if r.get("Email")
        and r.get("ARIA_Status", "") not in SKIP_STATUSES
        and not (r.get("Source", "") or "").startswith("guessed")
    ]
    logger.info(f"Uygun contact sayısı: {len(candidates)} (limit: {limit})")

    to_send = candidates[:limit]
    sent = 0
    skipped = 0
    errors = []

    for i, row in enumerate(to_send):
        email        = row.get("Email", "").strip()
        name         = row.get("Company_Name", "")
        sector       = row.get("Sector", "")
        osb          = row.get("OSB", "")
        contact_name = row.get("Contact_Name", "")
        domain       = row.get("Domain", "")

        if not email:
            skipped += 1
            continue

        first_name = ""
        last_name  = ""
        if contact_name:
            parts = contact_name.strip().split()
            first_name = parts[0] if parts else ""
            last_name  = parts[-1] if len(parts) > 1 else ""

        # Use fallback personalization (no Claude API cost)
        personalized_line = _fallback_personalized_line(name, sector, osb)

        logger.info(f"[{i+1}/{len(to_send)}] {name} <{email}>")
        logger.info(f"  Personalization: {personalized_line[:80]}")

        if dry_run:
            logger.info("  [DRY RUN] atlandı")
            sent += 1
            continue

        result = instantly.add_contact(
            email=email,
            first_name=first_name,
            last_name=last_name,
            company_name=name,
            personalized_line=personalized_line,
            sector=sector,
            osb=osb,
        )

        if result:
            sent += 1
            logger.info(f"  Eklendi ✓")
        else:
            skipped += 1
            errors.append(f"Instantly hatası: {name} <{email}>")
            logger.warning(f"  Instantly'e eklenemedi — {name}")

        time.sleep(1)  # Rate limiting

    logger.info(f"=== Bitti: {sent} eklendi, {skipped} atlandı, {len(errors)} hata ===")

    if not dry_run:
        summary_errors = errors[:3] if errors else None
        telegram.send_daily_summary(
            new_prospects_found=len(candidates),
            emails_sent=sent,
            replies_today=0,
            hot_leads_today=0,
            errors=summary_errors,
        )

    return {"sent": sent, "skipped": skipped, "errors": len(errors)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ARIA Resend from Sheet")
    parser.add_argument("--dry-run", action="store_true", help="Göster, gönderme")
    parser.add_argument("--limit", type=int, default=30, help="Max kaç contact (default: 30)")
    args = parser.parse_args()
    run(dry_run=args.dry_run, limit=args.limit)
