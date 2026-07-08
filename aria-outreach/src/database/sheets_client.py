"""
Google Sheets client — single source of truth for all ARIA prospect data.

Master sheet structure (tab: "ARIA_Prospects"):
  Company_Name, Sector, Domain, Phone, Address, OSB,
  Contact_Name, Email, Source, Added_Date,
  ARIA_Status, Email1_Date, Email2_Date, Email3_Date,
  Instantly_Contact_ID, Reply_Date, Reply_Category, Hot_Lead
"""

import json
import logging
from datetime import datetime, date
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

SHEET_TAB = "ARIA_Prospects"
META_TAB  = "ARIA_Meta"      # Stores timestamps, run logs

COLUMNS = [
    "Company_Name", "Sector", "Domain", "Phone", "Address", "OSB",
    "Contact_Name", "Email", "Source", "Added_Date",
    "ARIA_Status", "Email1_Date", "Email2_Date", "Email3_Date",
    "Instantly_Contact_ID", "Reply_Date", "Reply_Category", "Hot_Lead",
]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


class SheetsClient:
    def __init__(self, service_account_json: str, sheet_id: str):
        creds_dict = json.loads(service_account_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        self._gc = gspread.authorize(creds)
        self._sheet_id = sheet_id
        self._spreadsheet = None
        self._ws = None           # ARIA_Prospects worksheet
        self._meta_ws = None      # ARIA_Meta worksheet

    # ------------------------------------------------------------------ #
    #  Connection + setup                                                  #
    # ------------------------------------------------------------------ #

    def connect(self):
        """Open the spreadsheet and ensure required tabs exist."""
        self._spreadsheet = self._gc.open_by_key(self._sheet_id)
        self._ws = self._ensure_tab(SHEET_TAB, COLUMNS)
        self._meta_ws = self._ensure_tab(META_TAB, ["Key", "Value"])

    def _ensure_tab(self, tab_name: str, headers: list[str]) -> gspread.Worksheet:
        """Return worksheet, creating it with headers if it doesn't exist."""
        try:
            ws = self._spreadsheet.worksheet(tab_name)
            # Ensure headers match (non-destructive check)
            existing = ws.row_values(1)
            if not existing:
                ws.insert_row(headers, index=1)
        except gspread.WorksheetNotFound:
            ws = self._spreadsheet.add_worksheet(title=tab_name, rows=5000, cols=len(headers))
            ws.insert_row(headers, index=1)
            logger.info(f"Created sheet tab: {tab_name}")
        return ws

    # ------------------------------------------------------------------ #
    #  Prospect reading                                                    #
    # ------------------------------------------------------------------ #

    def get_existing_domains(self) -> set[str]:
        """Return set of all domains already in the master sheet (for dedup)."""
        records = self._ws.get_all_records()
        return {r["Domain"].lower().strip() for r in records if r.get("Domain")}

    def get_existing_company_names(self) -> set[str]:
        """Return set of normalized company names already in the master sheet."""
        records = self._ws.get_all_records()
        return {
            r["Company_Name"].lower().strip()
            for r in records if r.get("Company_Name")
        }

    def get_prospects_to_contact(self, limit: int = 50) -> list[dict]:
        """
        Return prospects ready for first outreach:
        - ARIA_Status is blank (never touched)
        - Have a valid email
        """
        records = self._ws.get_all_records()
        ready = [
            r for r in records
            if not r.get("ARIA_Status") and r.get("Email")
        ]
        return ready[:limit]

    def get_prospects_for_followup(self, days_since_email1: int = 4, limit: int = 50) -> list[dict]:
        """Return prospects due for follow-up 1 (Email1 sent N days ago, no reply)."""
        from datetime import timedelta
        records = self._ws.get_all_records()
        cutoff = (datetime.utcnow() - timedelta(days=days_since_email1)).date()
        due = []
        for r in records:
            if r.get("ARIA_Status") == "Email1_Sent" and r.get("Email1_Date"):
                try:
                    sent_date = datetime.strptime(r["Email1_Date"], "%Y-%m-%d").date()
                    if sent_date <= cutoff:
                        due.append(r)
                except ValueError:
                    pass
        return due[:limit]

    def get_all_records(self) -> list[dict]:
        return self._ws.get_all_records()

    # ------------------------------------------------------------------ #
    #  Prospect writing                                                    #
    # ------------------------------------------------------------------ #

    def add_prospects(self, prospects: list[dict]) -> int:
        """Batch-append new prospect rows. Returns count added."""
        if not prospects:
            return 0
        today = date.today().isoformat()
        rows = []
        for p in prospects:
            row = [
                p.get("Company_Name", ""),
                p.get("Sector", ""),
                p.get("Domain", ""),
                p.get("Phone", ""),
                p.get("Address", ""),
                p.get("OSB", ""),
                p.get("Contact_Name", ""),
                p.get("Email", ""),
                p.get("Source", "scraper"),
                today,
                "",  # ARIA_Status
                "", "", "",  # Email dates
                "",  # Instantly_Contact_ID
                "", "", "",  # Reply fields
            ]
            rows.append(row)
        self._ws.append_rows(rows, value_input_option="USER_ENTERED")
        logger.info(f"Added {len(rows)} prospects to sheet")
        return len(rows)

    def update_status(self, domain: str, fields: dict[str, Any], email: str = ""):
        """
        Update one or more columns for the row matching the given domain.
        Falls back to matching by email when domain is empty (e.g. NOSAB companies).
        """
        records = self._ws.get_all_records()
        domain_key = domain.lower().strip()
        email_key  = email.lower().strip()

        for i, record in enumerate(records, start=2):  # row 1 = header
            row_domain = record.get("Domain", "").lower().strip()
            row_email  = record.get("Email", "").lower().strip()

            match = (domain_key and row_domain == domain_key) or \
                    (email_key  and row_email  == email_key  and not domain_key)

            if match:
                for col_name, value in fields.items():
                    if col_name in COLUMNS:
                        col_idx = COLUMNS.index(col_name) + 1
                        self._ws.update_cell(i, col_idx, value)
                return True

        logger.warning(f"Row not found for update: domain={domain!r} email={email!r}")
        return False

    # ------------------------------------------------------------------ #
    #  Meta / timestamps                                                   #
    # ------------------------------------------------------------------ #

    def get_meta(self, key: str) -> str:
        """Read a meta value (e.g. last_reply_check timestamp)."""
        records = self._meta_ws.get_all_records()
        for r in records:
            if r.get("Key") == key:
                return r.get("Value", "")
        return ""

    def set_meta(self, key: str, value: str):
        """Write a meta key-value pair."""
        records = self._meta_ws.get_all_records()
        for i, r in enumerate(records, start=2):
            if r.get("Key") == key:
                self._meta_ws.update_cell(i, 2, value)
                return
        self._meta_ws.append_row([key, value])

    # ------------------------------------------------------------------ #
    #  Stats for weekly report                                             #
    # ------------------------------------------------------------------ #

    def get_weekly_stats(self) -> dict:
        """Summarize this week's outreach activity."""
        from datetime import timedelta
        records = self._ws.get_all_records()
        week_ago = (datetime.utcnow() - timedelta(days=7)).date()

        sent_this_week = 0
        replied = 0
        hot_leads = 0
        sector_counts: dict[str, int] = {}

        for r in records:
            e1 = r.get("Email1_Date", "")
            if e1:
                try:
                    d = datetime.strptime(e1, "%Y-%m-%d").date()
                    if d >= week_ago:
                        sent_this_week += 1
                        sector = r.get("Sector", "Diğer")
                        sector_counts[sector] = sector_counts.get(sector, 0) + 1
                except ValueError:
                    pass
            if r.get("Reply_Date"):
                replied += 1
            if r.get("Hot_Lead") == "YES":
                hot_leads += 1

        top_sector = max(sector_counts, key=sector_counts.get) if sector_counts else "—"
        return {
            "sent_this_week": sent_this_week,
            "replied": replied,
            "hot_leads": hot_leads,
            "top_sector": top_sector,
            "sector_breakdown": sector_counts,
        }
