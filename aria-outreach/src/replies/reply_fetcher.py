"""
Reply fetcher — polls Instantly.ai every 2 hours for new replies.
Uses Google Sheets meta tab to track last-check timestamp so nothing is missed
and nothing is processed twice.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

LAST_CHECK_KEY = "last_reply_check"


class ReplyFetcher:
    def __init__(self, instantly_client, sheets_client):
        self._instantly = instantly_client
        self._sheets = sheets_client

    def fetch_new_replies(self) -> list[dict]:
        """
        Fetch replies received since the last check.
        Updates the timestamp after fetching.
        Returns list of reply dicts from InstantlyClient.
        """
        last_check = self._sheets.get_meta(LAST_CHECK_KEY)
        logger.info(f"Fetching replies since: {last_check or 'beginning'}")

        replies = self._instantly.get_replies(since_timestamp=last_check)

        # Update timestamp immediately (even if 0 replies — prevents re-processing)
        now = datetime.now(timezone.utc).isoformat()
        self._sheets.set_meta(LAST_CHECK_KEY, now)

        logger.info(f"Found {len(replies)} new replies")
        return replies
