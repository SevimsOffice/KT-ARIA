"""
Company researcher — fetches the company's website and extracts
operational context using Claude Haiku. This feeds the personalizer.
"""

import logging
import re
import time

import anthropic
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

MAX_WEBSITE_CHARS = 3000
REQUEST_TIMEOUT   = 10

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}


class CompanyResearcher:
    def __init__(self, anthropic_api_key: str):
        self._client = anthropic.Anthropic(api_key=anthropic_api_key)
        self._prompt = _load_research_prompt()

    def research(self, company_name: str, domain: str, sector: str = "", osb: str = "") -> dict:
        """
        Research a company and return structured context.
        Returns:
          main_activity: str
          likely_pain_points: str
          ai_readiness_signal: str
          website_snippet: str  (raw text used)
        """
        website_text = _fetch_website_text(domain) if domain else ""

        prompt = self._prompt.format(
            company_name=company_name,
            domain=domain,
            sector=sector,
            osb=osb,
            website_text=website_text[:MAX_WEBSITE_CHARS] if website_text else "Web sitesi erişilemedi.",
            MAX_CHARS=MAX_WEBSITE_CHARS,
        )

        try:
            message = self._client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text.strip()
            return _parse_research_response(raw, website_text)
        except anthropic.APIError as e:
            logger.warning(f"Claude research error for {company_name}: {e}")
            return _fallback_research(company_name, sector, osb)


def _fetch_website_text(domain: str) -> str:
    """Fetch company homepage and extract readable text."""
    for prefix in [f"https://{domain}", f"https://www.{domain}", f"http://{domain}"]:
        try:
            time.sleep(1)
            resp = requests.get(prefix, timeout=REQUEST_TIMEOUT, headers=HEADERS)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                # Remove scripts and styles
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                text = soup.get_text(separator=" ")
                # Normalize whitespace
                text = re.sub(r"\s+", " ", text).strip()
                return text
        except Exception:
            continue
    return ""


def _parse_research_response(raw: str, website_text: str) -> dict:
    """Parse Claude's structured response."""
    result = {
        "main_activity": "",
        "likely_pain_points": "",
        "ai_readiness_signal": "",
        "website_snippet": website_text[:500],
    }
    lines = raw.split("\n")
    for line in lines:
        line = line.strip()
        if line.startswith("ANA_FAALIYET:"):
            result["main_activity"] = line.replace("ANA_FAALIYET:", "").strip()
        elif line.startswith("SORUN_NOKTALARI:"):
            result["likely_pain_points"] = line.replace("SORUN_NOKTALARI:", "").strip()
        elif line.startswith("AI_HAZIRLIK:"):
            result["ai_readiness_signal"] = line.replace("AI_HAZIRLIK:", "").strip()
    # Fallback: use full raw if parsing failed
    if not result["main_activity"]:
        result["main_activity"] = raw[:200]
    return result


def _fallback_research(company_name: str, sector: str, osb: str) -> dict:
    """Return generic context when website fetch or Claude fails."""
    return {
        "main_activity": f"{sector or 'üretim'} sektöründe faaliyet gösteren {osb} firması",
        "likely_pain_points": "e-posta yönetimi, raporlama, veri analizi",
        "ai_readiness_signal": "orta",
        "website_snippet": "",
    }


def _load_research_prompt() -> str:
    """Load from file or use embedded default."""
    try:
        with open("templates/prompts/research.txt", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return _DEFAULT_RESEARCH_PROMPT


_DEFAULT_RESEARCH_PROMPT = """Aşağıdaki firma hakkında kısa bir analiz yap. Sadece verilen bilgileri kullan.

Firma: {company_name}
Domain: {domain}
Sektör: {sector}
OSB: {osb}

Web sitesi içeriği:
{website_text}

Şu format ile yanıt ver (başka bir şey yazma):
ANA_FAALIYET: [Firmanın ana üretim/hizmet faaliyeti - 1 cümle]
SORUN_NOKTALARI: [Bu sektörde yaygın operasyonel sorunlar - max 10 kelime]
AI_HAZIRLIK: [düşük / orta / yüksek - web sitesine göre tahmin]"""
