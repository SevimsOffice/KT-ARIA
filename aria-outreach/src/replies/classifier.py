"""
Reply classifier — Claude Haiku reads incoming replies and categorizes them.
Categories drive automation: HOT gets instant Telegram alert,
WARM gets follow-up draft, COLD + UNSUBSCRIBE update sheet and stop.
"""

import json
import logging

import anthropic

logger = logging.getLogger(__name__)

CATEGORIES = {
    "HOT":          "Toplantı veya görüşme istiyor / fiyat soruyor / hemen ilgileniyor",
    "WARM":         "İlgili ama şu an uygun değil / başka birine yönlendiriyor / soru soruyor",
    "COLD":         "Nazikçe reddediyor / ilgi yok",
    "UNSUBSCRIBE":  "E-posta listesinden çıkmak istiyor / 'bir daha yazma' diyor",
    "OUT_OF_OFFICE": "Otomatik yanıt / tatilde / ofis dışında mesajı",
}


class ReplyClassifier:
    def __init__(self, anthropic_api_key: str):
        self._client = anthropic.Anthropic(api_key=anthropic_api_key)
        self._prompt = _load_classify_prompt()

    def classify(self, reply_body: str, from_email: str = "") -> dict:
        """
        Classify a reply email.
        Returns:
          category: HOT | WARM | COLD | UNSUBSCRIBE | OUT_OF_OFFICE
          summary: Short Turkish explanation (1 sentence)
          suggested_response: Draft response for HOT/WARM (Turkish)
          confidence: 0-100
        """
        if not reply_body or len(reply_body.strip()) < 5:
            return _make_result("COLD", "Boş yanıt", "", 90)

        # Quick heuristics for obvious cases
        body_lower = reply_body.lower()
        if _is_out_of_office(body_lower):
            return _make_result("OUT_OF_OFFICE", "Otomatik yanıt / ofis dışı mesajı", "", 95)
        if _is_unsubscribe(body_lower):
            return _make_result("UNSUBSCRIBE", "E-postadan çıkmak istiyor", "", 98)

        prompt = self._prompt.format(
            reply_body=reply_body[:1500],
            from_email=from_email,
        )

        try:
            message = self._client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text.strip()
            return _parse_classification(raw)
        except anthropic.APIError as e:
            logger.warning(f"Classification error: {e}")
            return _make_result("WARM", "Sınıflandırma hatası — manuel kontrol önerilir", "", 30)


def _is_out_of_office(body: str) -> bool:
    indicators = [
        "out of office", "ofis dışında", "tatil", "izinde", "absent",
        "otomatik yanıt", "automatic reply", "auto-reply", "autoresponder",
        "dönüşüm süresi", "geri döneceğim",
    ]
    return any(ind in body for ind in indicators)


def _is_unsubscribe(body: str) -> bool:
    indicators = [
        "unsubscribe", "listemden çıkar", "e-posta gönderme", "iletişime geçme",
        "bir daha yazma", "silmenizi", "kaldırın", "spam", "şikayet"
    ]
    return any(ind in body for ind in indicators)


def _parse_classification(raw: str) -> dict:
    """Parse Claude's JSON response."""
    # Try JSON parse first
    try:
        # Claude sometimes wraps in code blocks
        raw_clean = raw.strip().strip("```json").strip("```").strip()
        data = json.loads(raw_clean)
        category = data.get("category", "WARM").upper()
        if category not in CATEGORIES:
            category = "WARM"
        return _make_result(
            category=category,
            summary=data.get("summary", ""),
            suggested_response=data.get("suggested_response", ""),
            confidence=int(data.get("confidence", 70)),
        )
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: look for keywords in raw text
    raw_upper = raw.upper()
    for cat in ["HOT", "WARM", "COLD", "UNSUBSCRIBE", "OUT_OF_OFFICE"]:
        if cat in raw_upper:
            return _make_result(cat, raw[:200], "", 60)
    return _make_result("WARM", raw[:200], "", 40)


def _make_result(category: str, summary: str, suggested_response: str, confidence: int) -> dict:
    return {
        "category": category,
        "summary": summary,
        "suggested_response": suggested_response,
        "confidence": confidence,
    }


def _load_classify_prompt() -> str:
    try:
        with open("templates/prompts/classify_reply.txt", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return _DEFAULT_CLASSIFY_PROMPT


_DEFAULT_CLASSIFY_PROMPT = """Bir satış e-postasına gelen yanıtı sınıflandır.

Yanıt metni:
{reply_body}

Gönderen: {from_email}

Kategoriler:
- HOT: Toplantı/görüşme istiyor, fiyat soruyor, hemen ilgileniyor
- WARM: İlgili ama şu an hazır değil, soru soruyor, başka birine yönlendiriyor
- COLD: Nazikçe reddediyor veya ilgi göstermiyor
- UNSUBSCRIBE: E-postadan çıkmak istiyor
- OUT_OF_OFFICE: Otomatik yanıt

Şu JSON formatında yanıt ver (başka hiçbir şey yazma):
{{
  "category": "HOT/WARM/COLD/UNSUBSCRIBE/OUT_OF_OFFICE",
  "summary": "Tek cümle Türkçe açıklama",
  "suggested_response": "Eğer HOT veya WARM ise kısa bir Türkçe yanıt taslağı, değilse boş string",
  "confidence": 85
}}"""
