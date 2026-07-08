"""
Instantly.ai API client — adds contacts to campaigns and fetches replies.
Instantly handles all sequence logic (timing, follow-ups, unsubscribes).

API versions:
  v1 (legacy) — GET endpoints still work with ?api_key= query param
  v2 (current) — POST /leads requires Authorization: Bearer header
"""

import logging
import time

import requests

logger = logging.getLogger(__name__)

# v1 still works for read-only GET endpoints (campaign list, stats, replies)
INSTANTLY_V1 = "https://api.instantly.ai/api/v1"
# v2 required for write operations (add leads)
INSTANTLY_V2 = "https://api.instantly.ai/api/v2"


class InstantlyClient:
    def __init__(self, api_key: str, campaign_id: str):
        self._api_key    = api_key
        self._campaign_id = campaign_id

        # v2 uses Bearer token for all requests
        self._headers_v2 = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        # v1 uses Bearer too but also passes api_key in query params for GET
        self._headers_v1 = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

    def _v1_params(self, extra: dict = None) -> dict:
        """Query params for v1 GET requests."""
        p = {"api_key": self._api_key}
        if extra:
            p.update(extra)
        return p

    # ------------------------------------------------------------------ #
    #  Contact management (v2)                                             #
    # ------------------------------------------------------------------ #

    def add_contact(
        self,
        email: str,
        first_name: str = "",
        last_name: str = "",
        company_name: str = "",
        personalized_line: str = "",
        sector: str = "",
        osb: str = "",
    ) -> dict | None:
        """
        Add a contact to the active campaign via Instantly API v2.

        v2 endpoint: POST /api/v2/leads
        Auth: Authorization: Bearer {api_key}
        Personalization: {{personalization}} variable in email template.
        """
        payload = {
            "campaign_id":    self._campaign_id,
            "email":          email,
            "first_name":     first_name or "",
            "last_name":      last_name or "",
            "company_name":   company_name or "",
            # {{personalization}} is the standard Instantly custom variable
            "personalization": personalized_line,
            # Additional custom variables (available as {{sector}}, {{osb}} in templates)
            "variables": {
                "sector": sector,
                "osb":    osb,
            },
        }

        try:
            logger.info(f"Instantly v2 POST /leads payload: {payload}")
            print(f"[INSTANTLY] POST /leads payload: {payload}", flush=True)
            resp = requests.post(
                f"{INSTANTLY_V2}/leads",
                json=payload,
                headers=self._headers_v2,
                timeout=20,
            )
            print(f"[INSTANTLY] {resp.status_code} {email} | {resp.text}", flush=True)
            logger.info(f"Instantly v2 HTTP {resp.status_code} for {email}: {resp.text}")

            if resp.status_code == 429:
                logger.warning("Instantly rate limit — waiting 60s")
                time.sleep(60)
                return None
            if resp.status_code == 401:
                logger.error(
                    "Instantly 401 Unauthorized. Your API key may be wrong or expired.\n"
                    "Go to Instantly dashboard → Settings → API Keys → copy the key → "
                    "update INSTANTLY_API_KEY in GitHub Secrets."
                )
                return None
            if resp.status_code == 404:
                logger.error(
                    f"Instantly 404 — campaign not found.\n"
                    f"Current INSTANTLY_CAMPAIGN_ID: {self._campaign_id}\n"
                    "Go to Instantly → your campaign URL → copy the UUID from the URL."
                )
                return None
            if resp.status_code == 400:
                logger.error(f"Instantly 400 Bad Request for {email}: {resp.text}")
                return None
            if resp.status_code == 422:
                # Contact already exists — treat as success (idempotent)
                logger.info(f"Instantly: contact {email} already exists in campaign")
                return {"status": "already_exists"}

            resp.raise_for_status()
            data = resp.json()
            logger.info(f"Instantly: contact added ✓ {email}")
            return data if data else {"status": "ok"}

        except requests.RequestException as e:
            logger.error(f"Instantly add_contact error for {email}: {e}")
            return None

    # ------------------------------------------------------------------ #
    #  Campaign stats (v1 GET — still works)                              #
    # ------------------------------------------------------------------ #

    def get_campaign_stats(self) -> dict:
        """Fetch high-level campaign statistics."""
        try:
            resp = requests.get(
                f"{INSTANTLY_V1}/analytics/campaign/summary",
                params=self._v1_params({"campaign_id": self._campaign_id}),
                headers=self._headers_v1,
                timeout=15,
            )
            print(f"[INSTANTLY] GET /analytics/campaign/summary {resp.status_code} | {resp.text}", flush=True)
            logger.info(f"Instantly GET /analytics/campaign/summary {resp.status_code}: {resp.text}")
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.warning(f"Instantly stats error: {e}")
            return {}

    # ------------------------------------------------------------------ #
    #  Reply fetching (v1 GET — still works)                              #
    # ------------------------------------------------------------------ #

    def get_replies(self, since_timestamp: str = "") -> list[dict]:
        """
        Fetch replies received since a given ISO timestamp.
        Returns list of reply objects:
          {from_email, subject, body, lead_email, reply_time, email_id}
        """
        try:
            params = self._v1_params({
                "campaign_id": self._campaign_id,
                "limit": 100,
            })
            resp = requests.get(
                f"{INSTANTLY_V1}/unibox/emails",
                params=params,
                headers=self._headers_v1,
                timeout=20,
            )
            print(f"[INSTANTLY] GET /unibox/emails {resp.status_code} | {resp.text}", flush=True)
            logger.info(f"Instantly GET /unibox/emails {resp.status_code}: {resp.text}")
            resp.raise_for_status()
            data  = resp.json()
            emails = data.get("emails", data) if isinstance(data, dict) else data

            replies = []
            for email in emails:
                if email.get("email_type") not in ("reply", "inbound", 1, "1"):
                    continue
                if since_timestamp:
                    reply_time = email.get("created_at", email.get("timestamp", ""))
                    if reply_time and reply_time <= since_timestamp:
                        continue
                replies.append({
                    "from_email": email.get("from_address", email.get("from_email", "")),
                    "subject":    email.get("subject", ""),
                    "body":       _clean_reply_body(email.get("body", email.get("text", ""))),
                    "lead_email": email.get("lead_email", email.get("to_address", "")),
                    "reply_time": email.get("created_at", email.get("timestamp", "")),
                    "email_id":   email.get("id", ""),
                })
            return replies

        except requests.RequestException as e:
            logger.error(f"Instantly get_replies error: {e}")
            return []

    def get_leads_count(self) -> int:
        """How many leads are currently in the campaign."""
        try:
            resp = requests.get(
                f"{INSTANTLY_V1}/lead/list",
                params=self._v1_params({"campaign_id": self._campaign_id, "limit": 1}),
                headers=self._headers_v1,
                timeout=15,
            )
            print(f"[INSTANTLY] GET /lead/list {resp.status_code} | {resp.text}", flush=True)
            logger.info(f"Instantly GET /lead/list {resp.status_code}: {resp.text}")
            resp.raise_for_status()
            return resp.json().get("total", 0)
        except requests.RequestException:
            return 0

    def get_campaign_status(self) -> dict:
        """
        Return the status of the configured campaign.
        Tries v2 API first (direct lookup by ID), falls back to v1 list scan.
        Possible status values: 'active', 'paused', 'draft', 'completed', 'not_found', 'unknown'
        """
        STATUS_MAP = {
            0:   "draft",
            1:   "active",
            2:   "paused",
            3:   "completed",
            4:   "running_subsequences",
            -1:  "accounts_unhealthy",
            -2:  "bounce_protect",
            -99: "suspended",
        }

        # --- Attempt 1: v2 direct lookup by campaign ID ---
        try:
            resp = requests.get(
                f"{INSTANTLY_V2}/campaigns/{self._campaign_id}",
                headers=self._headers_v2,
                timeout=15,
            )
            print(f"[INSTANTLY] GET /v2/campaigns/{self._campaign_id} {resp.status_code} | {resp.text}", flush=True)
            logger.info(f"Instantly GET /v2/campaigns/{self._campaign_id} {resp.status_code}: {resp.text}")
            if resp.status_code == 200:
                data = resp.json()
                raw = data.get("status", -1)
                return {
                    "found":                True,
                    "name":                 data.get("name", ""),
                    "status":               STATUS_MAP.get(raw, f"unknown({raw})"),
                    "raw_status":           raw,
                    "allow_risky_contacts": data.get("allow_risky_contacts", True),
                    "end_date":             data.get("end_date", ""),
                    "daily_limit":          data.get("daily_limit", 0),
                    "email_list":           data.get("email_list", []),
                }
            if resp.status_code == 404:
                logger.warning("v2 direct lookup returned 404 — campaign ID may be wrong")
                return {"found": False, "status": "not_found"}
        except requests.RequestException as e:
            logger.warning(f"v2 campaign lookup failed, falling back to v1 list: {e}")

        # --- Attempt 2: v1 list scan (fallback) ---
        try:
            resp = requests.get(
                f"{INSTANTLY_V1}/campaign/list",
                params=self._v1_params({"limit": 100}),
                headers=self._headers_v1,
                timeout=15,
            )
            print(f"[INSTANTLY] GET /v1/campaign/list {resp.status_code} | {resp.text}", flush=True)
            logger.info(f"Instantly GET /v1/campaign/list {resp.status_code}: {resp.text}")
            resp.raise_for_status()
            data = resp.json()
            campaigns = data if isinstance(data, list) else data.get("data", [])
            for c in campaigns:
                if c.get("id") == self._campaign_id:
                    raw = c.get("status", -1)
                    return {
                        "found": True,
                        "name": c.get("name", ""),
                        "status": STATUS_MAP.get(raw, f"unknown({raw})"),
                        "raw_status": raw,
                    }
            # List returned OK but campaign not in it — treat as unknown, not hard not_found
            logger.warning(f"Campaign {self._campaign_id} not found in v1 list ({len(campaigns)} campaigns returned)")
            return {"found": False, "status": "list_miss"}
        except requests.RequestException as e:
            logger.error(f"Instantly campaign status error (both v1+v2 failed): {e}")
            return {"found": False, "status": "error", "error": str(e)}

    def patch_campaign(self, fields: dict) -> bool:
        """Update campaign settings via PATCH /api/v2/campaigns/{id}."""
        try:
            resp = requests.patch(
                f"{INSTANTLY_V2}/campaigns/{self._campaign_id}",
                json=fields,
                headers=self._headers_v2,
                timeout=15,
            )
            print(f"[INSTANTLY] PATCH /v2/campaigns/{self._campaign_id} {resp.status_code} | {resp.text}", flush=True)
            logger.info(f"Instantly PATCH /v2/campaigns {resp.status_code}: {resp.text}")
            resp.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.warning(f"Instantly campaign PATCH failed: {e}")
            return False

    def activate_campaign(self) -> bool:
        """Launch/resume the campaign via POST /api/v2/campaigns/{id}/activate."""
        try:
            resp = requests.post(
                f"{INSTANTLY_V2}/campaigns/{self._campaign_id}/activate",
                json={},
                headers=self._headers_v2,
                timeout=15,
            )
            print(f"[INSTANTLY] POST /campaigns/{self._campaign_id}/activate {resp.status_code} | {resp.text}", flush=True)
            logger.info(f"Instantly activate_campaign {resp.status_code}: {resp.text}")
            if resp.status_code in (200, 201):
                return True
            logger.warning(f"activate_campaign unexpected status {resp.status_code}: {resp.text}")
            return False
        except requests.RequestException as e:
            logger.error(f"Instantly activate_campaign error: {e}")
            return False

    def list_accounts_v2(self) -> list[dict]:
        """
        List email sending accounts via GET /api/v2/accounts.
        Returns list of dicts with keys: email, status (1=active, 2=paused, -1=connection error).
        """
        try:
            resp = requests.get(
                f"{INSTANTLY_V2}/accounts",
                params={"limit": 100},
                headers=self._headers_v2,
                timeout=15,
            )
            print(f"[INSTANTLY] GET /v2/accounts {resp.status_code} | {resp.text[:300]}", flush=True)
            logger.info(f"Instantly GET /v2/accounts {resp.status_code}: {resp.text[:300]}")
            if resp.status_code != 200:
                return []
            data = resp.json()
            items = data.get("items", data) if isinstance(data, dict) else data
            return items if isinstance(items, list) else []
        except requests.RequestException as e:
            logger.error(f"Instantly list_accounts_v2 error: {e}")
            return []

    def resume_account(self, email: str) -> bool:
        """Resume a paused sending account via POST /api/v2/accounts/{email}/resume."""
        try:
            resp = requests.post(
                f"{INSTANTLY_V2}/accounts/{email}/resume",
                json={},
                headers=self._headers_v2,
                timeout=15,
            )
            print(f"[INSTANTLY] POST /v2/accounts/{email}/resume {resp.status_code} | {resp.text}", flush=True)
            logger.info(f"Instantly resume_account {email} {resp.status_code}: {resp.text}")
            return resp.status_code in (200, 201)
        except requests.RequestException as e:
            logger.error(f"Instantly resume_account {email} error: {e}")
            return False

    def list_sending_accounts(self) -> list[dict]:
        """List email sending accounts connected to Instantly (needed for campaign to send)."""
        try:
            resp = requests.get(
                f"{INSTANTLY_V1}/account/list",
                params=self._v1_params({"limit": 100}),
                headers=self._headers_v1,
                timeout=15,
            )
            print(f"[INSTANTLY] GET /account/list {resp.status_code} | {resp.text}", flush=True)
            logger.info(f"Instantly GET /account/list {resp.status_code}: {resp.text}")
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else data.get("data", [])
        except requests.RequestException as e:
            logger.error(f"Instantly sending accounts error: {e}")
            return []


def _clean_reply_body(body: str) -> str:
    """Strip quoted/forwarded content so only the new reply text remains."""
    if not body:
        return ""
    import re
    patterns = [
        r"-----Original Message-----.*",
        r"On .+wrote:.*",
        r"From:.*\nSent:.*\nTo:.*",
        r"_{10,}.*",
        r"> .*",
    ]
    for pattern in patterns:
        body = re.sub(pattern, "", body, flags=re.DOTALL | re.IGNORECASE)
    return body.strip()[:2000]
