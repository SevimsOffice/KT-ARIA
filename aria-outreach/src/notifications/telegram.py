"""
Telegram Bot notifications — Sevim's real-time window into ARIA.
Three notification types:
  1. HOT lead alert (immediate, full context)
  2. Daily morning summary
  3. Weekly intelligence report
"""

import logging
from datetime import date

import requests

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self._token = bot_token
        self._chat_id = chat_id
        self._url = TELEGRAM_API.format(token=bot_token)

    # ------------------------------------------------------------------ #
    #  HOT lead alert — sent immediately when classifier returns HOT      #
    # ------------------------------------------------------------------ #

    def send_hot_lead_alert(
        self,
        company_name: str,
        sector: str,
        osb: str,
        reply_text: str,
        summary: str,
        suggested_response: str,
        domain: str = "",
        contact_name: str = "",
    ):
        msg = (
            f"🔥 *SICAK LEAD — HEMEN YANIT VER*\n\n"
            f"🏭 *Firma:* {_esc(company_name)}\n"
            f"📦 *Sektör:* {_esc(sector)} | {_esc(osb)}\n"
        )
        if contact_name:
            msg += f"👤 *Kişi:* {_esc(contact_name)}\n"
        if domain:
            msg += f"🌐 {_esc(domain)}\n"
        msg += (
            f"\n📨 *Yanıt özeti:* {_esc(summary)}\n\n"
            f"*Gelen yanıt:*\n_{_esc(reply_text[:400])}_\n"
        )
        if suggested_response:
            msg += f"\n💬 *Önerilen yanıt:*\n{_esc(suggested_response[:500])}\n"
        self._send(msg)

    # ------------------------------------------------------------------ #
    #  Daily summary — sent after morning pipeline run                    #
    # ------------------------------------------------------------------ #

    def send_daily_summary(
        self,
        new_prospects_found: int,
        emails_sent: int,
        replies_today: int,
        hot_leads_today: int,
        errors: list[str] = None,
    ):
        today = date.today().strftime("%d %B %Y")
        status = "✅" if not errors else "⚠️"
        msg = (
            f"{status} *ARIA Günlük Özet — {today}*\n\n"
            f"🔍 Yeni firma bulundu: *{new_prospects_found}*\n"
            f"📤 Instantly kampanyasına eklendi: *{emails_sent}*\n"
            f"📬 Yeni yanıt: *{replies_today}*\n"
            f"🔥 Sıcak lead: *{hot_leads_today}*\n"
        )
        if errors:
            msg += f"\n⚠️ Hatalar:\n" + "\n".join(f"• {_esc(e)}" for e in errors[:3])
        self._send(msg)

    # ------------------------------------------------------------------ #
    #  Weekly intelligence report                                          #
    # ------------------------------------------------------------------ #

    def send_weekly_report(self, stats: dict):
        """
        stats keys: sent_this_week, replied, hot_leads, top_sector, sector_breakdown
        """
        msg = (
            f"📊 *ARIA Haftalık Rapor*\n\n"
            f"📤 Bu hafta gönderilen: *{stats.get('sent_this_week', 0)}*\n"
            f"📬 Toplam yanıt: *{stats.get('replied', 0)}*\n"
            f"🔥 Sıcak lead: *{stats.get('hot_leads', 0)}*\n"
            f"🏆 En çok yanıt veren sektör: *{_esc(stats.get('top_sector', '—'))}*\n"
        )
        breakdown = stats.get("sector_breakdown", {})
        if breakdown:
            msg += "\n*Sektör dağılımı:*\n"
            for sector, count in sorted(breakdown.items(), key=lambda x: -x[1])[:5]:
                msg += f"  • {_esc(sector)}: {count}\n"
        # Insight
        if stats.get("hot_leads", 0) == 0:
            msg += "\n💡 *Öneri:* Bu hafta sıcak lead yok. Konu satırlarını test etmeyi dene."
        elif stats.get("top_sector"):
            msg += f"\n💡 *Öneri:* {_esc(stats['top_sector'])} sektörü en çok yanıt veriyor — bu sektöre odaklanmaya devam et."
        self._send(msg)

    # ------------------------------------------------------------------ #
    #  WARM lead notice                                                    #
    # ------------------------------------------------------------------ #

    def send_warm_lead_notice(self, company_name: str, summary: str):
        msg = (
            f"🌡️ *ILIMLI LEAD*\n\n"
            f"🏭 {_esc(company_name)}\n"
            f"📝 {_esc(summary)}\n\n"
            f"_Otomatik takip mesajı 24 saat içinde gönderilecek._"
        )
        self._send(msg)

    # ------------------------------------------------------------------ #
    #  Internal                                                            #
    # ------------------------------------------------------------------ #

    def _send(self, text: str):
        try:
            payload = {
                "chat_id": self._chat_id,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            }
            resp = requests.post(self._url, json=payload, timeout=10)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Telegram send error: {e}")


def _esc(text: str) -> str:
    """Escape Markdown special chars for Telegram."""
    if not text:
        return ""
    for ch in ["*", "_", "`", "[", "]"]:
        text = text.replace(ch, f"\\{ch}")
    return text
