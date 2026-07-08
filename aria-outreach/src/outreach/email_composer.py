"""
Email composer — uses Claude Haiku to generate one personalized Turkish
opening sentence, then fills the email template with it.
"""

import logging
import re

import anthropic

logger = logging.getLogger(__name__)


class EmailComposer:
    def __init__(self, anthropic_api_key: str):
        self._client = anthropic.Anthropic(api_key=anthropic_api_key)
        self._personalize_prompt = _load_prompt("templates/prompts/personalize.txt")
        self._initial_template = _load_template("templates/email_initial_tr.txt")
        self._followup1_template = _load_template("templates/email_followup1_tr.txt")
        self._followup2_template = _load_template("templates/email_followup2_tr.txt")

    def compose_initial(
        self,
        company_name: str,
        sector: str,
        osb: str,
        main_activity: str,
        pain_points: str,
        contact_name: str = "",
        city: str = "",
    ) -> dict:
        """
        Returns dict with:
          subject: str
          body: str
          personalized_line: str
        """
        personalized_line = self._generate_personalized_line(
            company_name, sector, osb, main_activity, pain_points, city
        )
        salutation = _make_salutation(contact_name)
        body = self._initial_template.format(
            salutation=salutation,
            personalized_line=personalized_line,
            company_name=company_name,
            sector=sector,
        )
        subject = f"{company_name} için yatırım teşvik desteği"
        return {"subject": subject, "body": body, "personalized_line": personalized_line}

    def compose_followup1(self, company_name: str, sector: str, contact_name: str = "") -> dict:
        salutation = _make_salutation(contact_name)
        body = self._followup1_template.format(
            salutation=salutation,
            company_name=company_name,
            sector=sector,
        )
        return {"subject": f"Re: {company_name} — hızlı bir sorum vardı", "body": body}

    def compose_followup2(self, company_name: str, sector: str, contact_name: str = "") -> dict:
        salutation = _make_salutation(contact_name)
        sector_example = _get_sector_example(sector)
        body = self._followup2_template.format(
            salutation=salutation,
            company_name=company_name,
            sector=sector,
            sector_example=sector_example,
        )
        return {"subject": f"Son bir düşünce — {company_name}", "body": body}

    def _generate_personalized_line(
        self, company_name: str, sector: str, osb: str, main_activity: str, pain_points: str,
        city: str = "",
    ) -> str:
        prompt = self._personalize_prompt.format(
            company_name=company_name,
            sector=sector,
            osb=osb,
            city=city or osb,
            main_activity=main_activity,
            pain_points=pain_points,
        )
        try:
            message = self._client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}],
            )
            line = message.content[0].text.strip()
            # Remove quotes if Claude added them
            line = line.strip('"\'')
            return line
        except anthropic.APIError as e:
            logger.warning(f"Personalization failed for {company_name}: {e}")
            return _fallback_personalized_line(company_name, sector, osb)


def _make_salutation(contact_name: str) -> str:
    if not contact_name:
        return "Sayın Yetkili"
    parts = contact_name.strip().split()
    if parts:
        return f"Sayın {parts[-1]} Bey/Hanım"
    return "Sayın Yetkili"


def _get_sector_example(sector: str) -> str:
    sector_lower = sector.lower()
    examples = {
        "tekstil": "Yeni dokuma veya iplik makinesi yatırımında teşvik belgesiyle KDV istisnası ve gümrük muafiyetinden yararlanan tekstil üreticileri, yatırım maliyetini kayda değer oranda düşürüyor",
        "otomotiv": "Üretim hattını genişleten otomotiv yan sanayi firmaları, teşvik belgesi kapsamındaki SGK prim desteği ve vergi indiriminden yıllarca yararlanabiliyor",
        "metal": "CNC ve işleme merkezi yatırımı yapan metal sanayi firmaları, teşvik belgesiyle ithal makinelerde gümrük vergisi ödemeden yatırımlarını tamamlayabiliyor",
        "makine": "Kapasite artıran makine üreticileri, yatırım teşvik belgesiyle hem KDV istisnasından hem de bölgesel desteklerden aynı anda yararlanabiliyor",
        "gıda": "Yeni işleme ve paketleme hattı kuran gıda üreticileri, teşvik belgesi ve kalkınma ajansı destekleriyle yatırım yükünü önemli ölçüde hafifletebiliyor",
        "plastik": "Enjeksiyon makinesi parkını yenileyen plastik sanayicileri, teşvik belgesiyle KDV istisnası ve SGK prim desteğinden birlikte yararlanabiliyor",
    }
    for key, example in examples.items():
        if key in sector_lower:
            return example
    return "Makine ve kapasite yatırımı yapan imalat firmaları, yatırım teşvik belgesiyle KDV istisnası, gümrük muafiyeti ve SGK prim desteğinden yararlanabiliyor"


def _fallback_personalized_line(company_name: str, sector: str, osb: str) -> str:
    return (
        f"{osb}'deki {sector.lower()} üretiminizde planladığınız makine ve kapasite "
        f"yatırımlarında yararlanabileceğiniz destekleri değerlendirmek istedim."
    )


def _load_template(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "{salutation},\n\n{personalized_line}\n\n{body}\n"


def _load_prompt(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return _DEFAULT_PERSONALIZE_PROMPT


_DEFAULT_PERSONALIZE_PROMPT = """Türk bir şirkete satış e-postası için tek bir kişiselleştirilmiş açılış cümlesi yaz.

Firma: {company_name}
Sektör: {sector}
OSB: {osb}
Şehir: {city}
Ana Faaliyet: {main_activity}
Olası Sorunlar: {pain_points}

Kurallar:
- Sadece 1 cümle yaz, başka hiçbir şey ekleme
- Türkçe, resmi ama sıcak
- Firmanın spesifik faaliyetine değin
- "yapay zeka" veya "AI" kelimelerini kullanma
- Jenerik olmayan, bu firmaya özel bir gözlem içersin
- Maksimum 25 kelime"""
