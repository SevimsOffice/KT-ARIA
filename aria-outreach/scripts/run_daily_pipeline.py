"""
ARIA Daily Pipeline — runs every morning at 7 AM Turkey time via GitHub Actions.

Flow:
  1. Scrape NOSAB + DOSAB + KAYAPA OSB websites for new companies
  2. Deduplicate against master sheet
  3. Enrich each new company with email (Apollo → Hunter → guesser)
  4. Research each company website (Claude Haiku)
  5. Generate personalized email opening (Claude Haiku)
  6. Add to Instantly.ai campaign
  7. Update Google Sheets with status
  8. Send Telegram daily summary

Usage:
  python scripts/run_daily_pipeline.py
  python scripts/run_daily_pipeline.py --dry-run      (no sends, just print)
  python scripts/run_daily_pipeline.py --limit 10     (process only 10 new companies)
"""

import argparse
import logging
import os
import sys
import time

# Allow imports from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from src.config import get_config
from src.database.sheets_client import SheetsClient
from src.scraper.nosab_scraper import scrape_nosab, scrape_nosab_detail
from src.scraper.dosab_scraper import scrape_dosab
from src.scraper.kayapa_scraper import scrape_kayapa
from src.scraper.istanbul_scraper import scrape_istanbul
from src.scraper.izmir_scraper import scrape_izmir
from src.scraper.base_scraper import get_session
from src.scraper.deduplicator import merge_sources, deduplicate, validate_and_clean
from src.enrichment.apollo_client import ApolloClient
from src.enrichment.hunter_client import HunterClient
from src.enrichment.email_guesser import best_guess
from src.enrichment.website_scraper import WebsiteEmailScraper
from src.research.company_researcher import CompanyResearcher
from src.outreach.email_composer import EmailComposer
from src.outreach.instantly_client import InstantlyClient
from src.notifications.telegram import TelegramNotifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("aria.daily")


def run(dry_run: bool = False, limit: int = 100):
    logger.info(f"=== ARIA Daily Pipeline {'(DRY RUN) ' if dry_run else ''}===")

    cfg = get_config()
    errors = []

    # --- Clients ---
    sheets = SheetsClient(cfg.google_service_account_json, cfg.google_sheet_id)
    sheets.connect()

    apollo = ApolloClient(cfg.apollo_api_key) if cfg.apollo_api_key else None
    hunter = HunterClient(cfg.hunter_api_key) if cfg.hunter_api_key else None
    website_scraper = WebsiteEmailScraper()
    researcher = CompanyResearcher(cfg.anthropic_api_key)
    composer = EmailComposer(cfg.anthropic_api_key)
    instantly = InstantlyClient(cfg.instantly_api_key, cfg.instantly_campaign_id)
    telegram = TelegramNotifier(cfg.telegram_bot_token, cfg.telegram_chat_id)

    # --- Pre-flight: verify Instantly campaign is active ---
    campaign_info   = instantly.get_campaign_status()
    campaign_status = campaign_info.get("status", "unknown")
    campaign_name   = campaign_info.get("name", "?")

    if campaign_info.get("found"):
        # Auto-fix campaign settings before checking status
        import datetime as _dt
        patches = {}
        # NOTE: allow_risky_contacts intentionally NOT patched — keep false to protect domain
        if campaign_info.get("daily_limit", 0) != 100:
            patches["daily_limit"] = 100
            logger.info(f"Pre-flight: daily_limit={campaign_info.get('daily_limit')} → auto-fixing to 100")
        end_date_str = campaign_info.get("end_date", "")
        if end_date_str:
            try:
                end = _dt.date.fromisoformat(end_date_str)
                days_left = (end - _dt.date.today()).days
                logger.info(f"Pre-flight: kampanya end_date={end_date_str} ({days_left} gün kaldı)")
                if days_left < 60:
                    new_end = (_dt.date.today() + _dt.timedelta(days=180)).isoformat()
                    patches["end_date"] = new_end
                    logger.info(f"Pre-flight: end_date yaklaşıyor → auto-extending to {new_end}")
            except ValueError:
                pass
        if patches:
            ok = instantly.patch_campaign(patches)
            logger.info(f"Pre-flight kampanya düzeltme: {'✓' if ok else '✗'} {patches}")
        # Activate campaign if not active (covers 'completed' too)
        if campaign_status != "active":
            logger.warning(f"Pre-flight: kampanya durumu='{campaign_status}' → aktivasyon deneniyor")
            act_ok = instantly.activate_campaign()
            logger.info(f"Pre-flight kampanya aktivasyonu: {'✓' if act_ok else '✗'}")
            if not act_ok:
                logger.warning("Kampanya aktivasyonu başarısız — pipeline yine de devam ediyor")
        # Resume any paused/errored sending accounts
        for acc in instantly.list_accounts_v2():
            acc_email  = acc.get("email", acc.get("username", ""))
            acc_status = acc.get("status", -99)
            if acc_status == 2 and acc_email:
                logger.info(f"Pre-flight: gönderici hesap paused → resume: {acc_email}")
                instantly.resume_account(acc_email)
            elif acc_status == -1 and acc_email:
                logger.warning(f"Pre-flight: {acc_email} bağlantı hatası — Instantly UI'dan yeniden bağla")
                errors.append(f"Gönderici hesap bağlantı hatası: {acc_email}")

        logger.info(f"Pre-flight OK: Instantly kampanya '{campaign_name}' ✓")
    else:
        # Could not confirm status (API list miss or v1/v2 both failed) — warn but continue.
        # The add_contact call itself will surface any real auth/ID errors.
        logger.warning(
            f"Kampanya durumu doğrulanamadı (status={campaign_status}) — "
            "pipeline devam ediyor, add_contact hataları varsa logda görünür."
        )

    # --- Step 1: Scrape ---
    logger.info("Step 1: Scraping OSB websites...")
    try:
        nosab = scrape_nosab()
        dosab = scrape_dosab()
        kayapa = scrape_kayapa()
        istanbul = scrape_istanbul()
        izmir = scrape_izmir()
        all_scraped = merge_sources([nosab, dosab, kayapa, istanbul, izmir])
        logger.info(f"Scraped total: {len(all_scraped)} companies")
    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        errors.append(f"Scraping error: {e}")
        all_scraped = []

    # --- Step 2: Deduplicate ---
    logger.info("Step 2: Deduplicating...")
    existing_domains = sheets.get_existing_domains()
    existing_names   = sheets.get_existing_company_names()
    fresh = deduplicate(all_scraped, existing_domains, existing_names)
    fresh = validate_and_clean(fresh)
    fresh = fresh[:limit]
    logger.info(f"New companies to process: {len(fresh)}")

    if dry_run:
        logger.info("[DRY RUN] First 5 new companies:")
        for c in fresh[:5]:
            logger.info(f"  {c['Company_Name']} | {c['Domain']} | {c['OSB']}")

    # --- Steps 3–6: Enrich → Research → Compose → Send ---
    emails_sent = 0
    new_prospects_added = 0

    # Shared session for NOSAB detail page fetching
    nosab_session = get_session()

    for i, company in enumerate(fresh):
        name    = company["Company_Name"]
        domain  = company.get("Domain", "")
        sector  = company.get("Sector", "")
        osb     = company.get("OSB", "")
        city    = company.get("City", "Bursa")

        logger.info(f"Processing [{i+1}/{len(fresh)}]: {name}")

        # Step 2.5: For NOSAB companies, fetch detail page to get email + domain
        # This runs BEFORE Apollo/Hunter so we use real contact data from the OSB site
        if osb == "NOSAB" and company.get("detail_url") and not company.get("Email"):
            logger.info(f"  Fetching NOSAB detail page for {name}")
            detail = scrape_nosab_detail(nosab_session, company["detail_url"])
            if detail.get("email"):
                company["Email"] = detail["email"]
                logger.info(f"  Found email from NOSAB detail: {detail['email']}")
            if detail.get("domain") and not domain:
                company["Domain"] = detail["domain"]
                domain = detail["domain"]
            if detail.get("phone") and not company.get("Phone"):
                company["Phone"] = detail["phone"]
            if detail.get("sector") and not sector:
                company["Sector"] = detail["sector"]
                sector = detail["sector"]

        # Step 3: Enrich email
        contact = None

        # Use email scraped directly from OSB site (highest quality — verified address)
        if company.get("Email"):
            contact = {
                "email":      company["Email"],
                "first_name": "",
                "last_name":  "",
                "title":      "",
                "source":     f"{osb.lower()}_direct",
            }
        else:
            # If no domain, derive one from the company name before trying APIs
            if not domain:
                from src.enrichment.email_guesser import guess_domain_from_company_name
                derived = guess_domain_from_company_name(name)
                if derived:
                    domain = derived
                    company["Domain"] = domain
                    logger.info(f"  Derived domain '{domain}' from company name")

            # Step 3a: Website scraper — real published emails (no guessing)
            if domain and not contact:
                contact = website_scraper.find_email(domain)

            # Step 3b: Apollo → Hunter (verified API sources)
            if domain and not contact:
                if apollo:
                    contact = apollo.find_contact_by_domain(domain, name)
                if not contact and hunter:
                    contact = hunter.find_email_by_domain(domain)

            # Step 3c: Pattern guesser — ONLY as last resort, will be skipped before send
            if not contact:
                contact = best_guess(domain=domain, company_name=name)

        if not contact or not contact.get("email"):
            logger.info(f"  No email found for {name} — skipping")
            continue

        email      = contact["email"]
        first_name = contact.get("first_name", "")
        last_name  = contact.get("last_name", "")
        title      = contact.get("title", "")
        source     = contact.get("source", "unknown")

        # Skip guessed/pattern emails — protect domain from bounces
        if source.startswith("guessed"):
            logger.info(f"  Skipping {name} — guessed email ({email}), not verified")
            continue

        company["Email"]        = email
        company["Contact_Name"] = f"{first_name} {last_name}".strip()
        company["Source"]       = source

        logger.info(f"  Email: {email} (source: {source})")

        # Step 4: Research company
        research = researcher.research(name, domain, sector, osb)

        # Step 5: Compose personalized email
        email_content = composer.compose_initial(
            company_name=name,
            sector=sector,
            osb=osb,
            city=city,
            main_activity=research["main_activity"],
            pain_points=research["likely_pain_points"],
            contact_name=f"{first_name} {last_name}".strip(),
        )

        logger.info(f"  Subject: {email_content['subject']}")
        logger.info(f"  Personalized line: {email_content['personalized_line'][:80]}...")

        if dry_run:
            logger.info(f"  [DRY RUN] Would add to Instantly campaign")
            new_prospects_added += 1
            continue

        # Step 6: Add to Instantly campaign
        result = instantly.add_contact(
            email=email,
            first_name=first_name,
            last_name=last_name,
            company_name=name,
            personalized_line=email_content["personalized_line"],
            sector=sector,
            osb=osb,
        )

        if result:
            emails_sent += 1
            new_prospects_added += 1
            # Update Google Sheet
            sheets.add_prospects([company])
            sheets.update_status(
                domain=domain,
                email=email,       # Fallback for NOSAB companies with no domain
                fields={
                    "ARIA_Status": "Added_to_Instantly",
                    "Email1_Date": __import__("datetime").date.today().isoformat(),
                },
            )
        else:
            errors.append(f"Instantly failed for {name}")

        time.sleep(0.5)  # Polite rate limiting

    # After adding leads, re-activate campaign in case it was in 'completed' state
    # (a campaign with no leads completes immediately; adding leads requires a new launch)
    if emails_sent > 0 and not dry_run:
        logger.info("Leads eklendi — kampanya tekrar aktive ediliyor (completed→active)")
        instantly.activate_campaign()

    # --- Step 7: Telegram summary ---
    logger.info(f"Pipeline complete: {emails_sent} added to campaign, {len(errors)} errors")

    if not dry_run:
        telegram.send_daily_summary(
            new_prospects_found=len(all_scraped),
            emails_sent=emails_sent,
            replies_today=0,  # Handled by reply_handler
            hot_leads_today=0,
            errors=errors if errors else None,
        )

    logger.info("=== Done ===")
    return {"sent": emails_sent, "new": new_prospects_added, "errors": len(errors)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ARIA Daily Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Run without sending anything")
    parser.add_argument("--limit", type=int, default=100, help="Max companies to process")
    args = parser.parse_args()
    run(dry_run=args.dry_run, limit=args.limit)
