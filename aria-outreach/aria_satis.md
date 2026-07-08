# ARIA Outreach — Çalışma Özeti

Bu belge, ARIA sistemi üzerinde yapılan tüm geliştirme ve hata düzeltme çalışmalarını özetler.

---

## Sistem Nedir?

ARIA, Türk OSB (Organize Sanayi Bölgesi) firmalarını otomatik olarak araştırıp kişiselleştirilmiş B2B e-posta gönderen bir outreach pipeline'ıdır.

**Akış:**
1. OSB web sitelerini scrape et → yeni firmalar bul
2. Google Sheets ile karşılaştır → mükerrer kayıtları çıkar
3. Apollo.io → Hunter.io → pattern guesser ile email bul
4. Claude Haiku ile şirket araştır + kişiselleştirilmiş email yaz
5. Instantly.ai kampanyasına ekle → otomatik gönderim
6. Google Sheets'e kaydet
7. Telegram ile günlük özet gönder

**GitHub Actions** her gün sabah 07:00 (Türkiye saati) pipeline'ı otomatik çalıştırır.

---

## Yapılan Çalışmalar

### 1. Instantly API Geçişi (v1 → v2)
**Sorun:** Instantly v1 `/lead/add` endpoint'i artık çalışmıyordu, 401 hatası alınıyordu.  
**Düzeltme:** Lead ekleme işlemi v2 `/leads` endpoint'ine taşındı, Bearer token auth eklendi.

---

### 2. Sosyal Medya Domain Filtresi
**Sorun:** Apollo/Hunter, `youtube.com`, `linkedin.com` gibi domainlere de sorgu atıyordu.  
**Düzeltme:** `_BLOCKED_DOMAINS` listesi hem Apollo hem Hunter client'larına eklendi.

---

### 3. Instantly Kampanya Durum Kontrolü
**Sorun:** Pipeline, kampanya ID'sini v1 listesinde bulamazsa hard-abort yapıyordu. Bu, Growth plan kullanan hesaplarda yanlış davranışa yol açıyordu.  
**Düzeltme:**
- v2 API ile direkt kampanya lookup eklendi (daha güvenilir)
- Kampanya listede bulunamazsa soft-warn yapılıp pipeline devam ediyor
- Kampanya pasif/durdurulmuş durumdaysa Telegram'a uyarı gönderilip çıkılıyor

---

### 4. DOSAB Firmaları için Apollo/Hunter Atlatma Hatası
**Sorun:** DOSAB Excel'indeki firmalar domain bilgisi içermiyor. Pipeline kodu `elif domain:` bloğuna girip Apollo/Hunter'ı çağırıyordu ama domain olmadığı için direkt pattern guesser'a atlıyordu. Hiçbir zaman gerçek API araması yapılmıyordu.  
**Düzeltme:** `else` bloğuna taşındı; domain yoksa önce şirket adından domain türetiliyor, sonra Apollo → Hunter → pattern guesser sırasıyla deneniyor:

```python
else:
    if not domain:
        derived = guess_domain_from_company_name(name)
        if derived:
            domain = derived
    if domain:
        if apollo:
            contact = apollo.find_contact_by_domain(domain, name)
        if not contact and hunter:
            contact = hunter.find_email_by_domain(domain)
    if not contact:
        contact = best_guess(domain=domain, company_name=name)
```

---

### 5. İstanbul ve İzmir OSB Scrapers Eklendi
**Sorun:** Pipeline sadece Bursa'daki 3 OSB'yi (NOSAB, DOSAB, KAYAPA) tarıyordu.  
**Eklenen dosyalar:**
- `src/scraper/istanbul_scraper.py` — İkitelli, Tuzla, Hadımköy, Dudullu OSB
- `src/scraper/izmir_scraper.py` — Kemalpaşa, Atatürk, Çiğli, Torbalı OSB

Her scraper Kayapa pattern'ini takip eder: birden fazla URL kombinasyonunu dener, site ulaşılamazsa boş liste döner (hata vermez).

**City alanı eklendi:** Tüm scraper'lar artık `City` alanı döndürüyor:
- NOSAB, DOSAB, KAYAPA → `City: "Bursa"`
- İstanbul scrapers → `City: "İstanbul"`
- İzmir scrapers → `City: "İzmir"`

---

### 6. Kişiselleştirilmiş Email'de Hardcode Düzeltmeleri
**Sorun:**
- `email_composer.py` içinde fallback metin `"benzer sektörde faaliyet gösteren bir Bursa firması"` hardcode'du
- `personalize.txt` prompt'unda `"DOSAB'daki dokuma üretiminde..."` örneği hardcode'du

**Düzeltme:**
- `compose_initial()` artık `city=` parametresi alıyor
- Prompt template'e `{city}` değişkeni eklendi
- Fallback metin `"benzer sektörde faaliyet gösteren bir OSB firması"` olarak güncellendi

---

### 7. Hunter Client `None` Crash Düzeltmesi
**Sorun:** Hunter.io API bazı kayıtlarda `"position": null` dönüyor. `e.get("position", "").lower()` ifadesi `None` üzerinde `.lower()` çağırdığı için `AttributeError` ile çöküyordu.  
**Düzeltme:**
```python
# Önce:
key=lambda e: any(t in e.get("position", "").lower() for t in priority_titles)

# Sonra:
key=lambda e: any(t in (e.get("position") or "").lower() for t in priority_titles)
```

---

### 8. Instantly Kampanya Ayarları Otomatik Düzeltme
**Sorun:**
- `allow_risky_contacts: false` → Pattern guesser ile oluşturulan tüm emailler (info@, iletisim@, vb.) Instantly tarafından sessizce reddediliyordu. **Hiçbir email gönderilmemesinin gerçek nedeni buydu.**
- `end_date: 2026-06-09` → Kampanya 6 gün sonra otomatik duracaktı.

**Düzeltme:**
- `InstantlyClient.get_campaign_status()` artık `allow_risky_contacts`, `end_date`, `daily_limit` değerlerini de döndürüyor
- `InstantlyClient.patch_campaign(fields)` metodu eklendi (`PATCH /api/v2/campaigns/{id}`)
- Pipeline pre-flight aşamasında otomatik kontrol ve düzeltme:
  - `allow_risky_contacts=false` ise → `true` yapılıyor
  - `end_date` 60 günden az kaldıysa → 180 gün uzatılıyor
- `scripts/fix_campaign.py` — tek seferlik çalıştırılabilir düzeltme scripti
- `.github/workflows/fix_campaign.yml` — manuel tetiklenebilir GitHub Actions workflow

---

## Mevcut Dosya Yapısı

```
aria-outreach/
├── scripts/
│   ├── run_daily_pipeline.py   # Ana pipeline (her gün 07:00'de çalışır)
│   ├── fix_campaign.py         # Instantly kampanya ayarlarını düzeltir
│   ├── diagnose.py             # Tüm bağlantıları test eder
│   ├── run_resend_from_sheet.py
│   └── run_weekly_report.py
├── src/
│   ├── scraper/
│   │   ├── nosab_scraper.py    # Nilüfer OSB — HTML A-Z listing
│   │   ├── dosab_scraper.py    # Demirtaş OSB — Excel download
│   │   ├── kayapa_scraper.py   # Kayapa OSB — multi-URL flexible
│   │   ├── istanbul_scraper.py # İkitelli, Tuzla, Hadımköy, Dudullu
│   │   ├── izmir_scraper.py    # Kemalpaşa, Atatürk, Çiğli, Torbalı
│   │   ├── base_scraper.py     # Ortak yardımcılar
│   │   └── deduplicator.py     # Mükerrer kayıt kontrolü
│   ├── enrichment/
│   │   ├── apollo_client.py    # Apollo.io email arama
│   │   ├── hunter_client.py    # Hunter.io email arama (fallback)
│   │   └── email_guesser.py    # Pattern tabanlı email tahmini (son çare)
│   ├── research/
│   │   └── company_researcher.py  # Claude Haiku ile şirket araştırma
│   ├── outreach/
│   │   ├── email_composer.py   # Claude Haiku ile kişiselleştirilmiş email
│   │   └── instantly_client.py # Instantly.ai API client
│   ├── database/
│   │   └── sheets_client.py    # Google Sheets CRM
│   ├── notifications/
│   │   └── telegram.py         # Telegram günlük özet
│   └── config.py
├── .github/workflows/
│   ├── daily_pipeline.yml      # Her gün 07:00 Türkiye saati
│   ├── fix_campaign.yml        # Manuel: kampanya ayarlarını düzelt
│   ├── diagnose.yml            # Manuel: bağlantı testi
│   ├── reply_handler.yml       # Her saat: yeni yanıtları işle
│   ├── resend_from_sheet.yml   # Manuel: sheet'ten tekrar gönder
│   └── weekly_report.yml       # Haftalık rapor
└── templates/
    ├── prompts/
    │   └── personalize.txt     # Claude Haiku kişiselleştirme prompt'u
    └── email_*.txt             # Email şablonları (TR)
```

---

---

## Neden Hiç Mail Gitmiyor? — Kök Neden Analizi (Haziran 2026)

Analytics sayfası "Total sent: 0", Leads sekmesi boş, kampanya "Completed" gösteriyor.
Üç farklı sorun aynı anda aktifti ve birbirini maskeliyordu.

---

### Sorun 1 — Kampanyada Hiç Lead Yok

**Ekran:** Leads sekmesi boş ("Add Leads" placeholder gösteriyor).

**Neden:** Pipeline geçmişte hiç lead Instantly'ye ekleyemedi. İki birbirini katlayan neden:
- Eski pipeline kodunda `campaign not found` → hard-abort; scraping hiç başlamıyordu.
- Verified email bulunamayan firmalar (guessed@ filtresi) Instantly'ye eklenmiyor; bu doğru bir koruma ama sonuç 0.

**Düzeltme:**
- `scripts/run_resend_from_sheet.py` — Google Sheets'teki mevcut doğrulanmış email'li firmalar Instantly'ye gönderilir (guessed@ filtresi burada da çalışır, domain korunur).
- Varsayılan limit 30'a çıkarıldı (hesap günlük limitiyle uyumlu).

---

### Sorun 2 — Kampanya "Completed" Durumunda

**Ekran:** Analytics → Status: `Completed`, %100 progress bar.

**Neden (iki katman):**
1. Lead'siz bir kampanya launch edilince Instantly anında "Completed" statüsüne çeker.
2. Kod `STATUS_MAP` yanlıştı: Instantly v2'de `3=completed`, `4=running_subsequences`; eski kodda `3="stopped"`, `4="completed"` yazıyordu. Bu yüzden `campaign_status != "active"` koşulu hiç doğru çalışmıyordu.
3. Aktivasyon yöntemi yanlıştı: `PATCH {"status": 1}` değil, Instantly'nin resmi yolu `POST /api/v2/campaigns/{id}/activate`.

**Düzeltme:**
```python
# Eski (yanlış) STATUS_MAP
{0: "draft", 1: "active", 2: "paused", 3: "stopped", 4: "completed"}

# Yeni (doğru) STATUS_MAP
{0: "draft", 1: "active", 2: "paused", 3: "completed", 4: "running_subsequences", ...}
```
- `InstantlyClient.activate_campaign()` → `POST /api/v2/campaigns/{id}/activate`
- Aktivasyon koşulu: `status != "active"` (completed dahil hepsi)
- Lead ekledikten sonra pipeline tekrar `activate_campaign()` çağırıyor (lead'siz completed → lead eklendi → yeniden launch)

---

### Sorun 3 — Gönderici Hesap PAUSED

**Ekran:** Email Accounts → `sevim@aiandtech-info.com` → **Paused**, `0 of 30 sent`.

**Neden:** Hesap warmup veya bağlantı kesintisi yüzünden otomatik duraklatıldı. Kampanya aktif olsa bile paused hesaptan mail çıkmaz.

**Düzeltme:**
- `InstantlyClient.list_accounts_v2()` — v2 `/accounts` ile hesap durumlarını listele
- `InstantlyClient.resume_account(email)` — `POST /api/v2/accounts/{email}/resume`
- `scripts/fix_campaign.py` ve `run_daily_pipeline.py` pre-flight'a eklendi: paused hesaplar otomatik resume edilir
- Hesap "connection error" (-1) ise: otomatik resume çalışmaz, kullanıcının Instantly UI → Email Accounts → Gmail'i yeniden bağlaması gerekir (log'da uyarı çıkar)

---

### Sorun 4 — Domain Bounce Koruması vs. Email Bulamama

Bu bir hata değil, bilinçli bir tasarım kararı. Ama etkisini bilmek gerekiyor:

| Email Kaynağı | Instantly'ye Ekleniyor mu? |
|---|---|
| OSB site'sinden direkt (nosab_direct) | ✅ Evet |
| Şirket web sitesinden (website scraper) | ✅ Evet |
| Apollo.io API (ücretli plan gerekir) | ✅ Evet |
| Hunter.io API (25/ay limit) | ✅ Evet |
| Pattern guesser (info@tahmin.com.tr) | ❌ Hayır — bounce koruması |

`allow_risky_contacts: false` intentionally korunuyor. Guessed email'ler pipeline'da ve resend script'inde filtreleniyor. Domain `aiandtech-info.com` korunuyor.

---

### Düzeltme Sırası (Haziran 2026)

1. `src/outreach/instantly_client.py` — STATUS_MAP düzeltildi, `activate_campaign()`, `list_accounts_v2()`, `resume_account()` metodları eklendi
2. `scripts/fix_campaign.py` — tam pre-send health check scripti (hesap, email_list, aktivasyon, lead sayısı)
3. `scripts/run_daily_pipeline.py` — pre-flight: doğru aktivasyon + hesap resume; post-loop: lead eklendikten sonra tekrar aktivasyon
4. `scripts/run_resend_from_sheet.py` — guessed email filtresi eklendi, limit 30'a çıkarıldı

**Çalıştırma sırası:**
1. GitHub Actions → **Fix Instantly Campaign** → hesap resume + kampanya aktive
2. GitHub Actions → **Resend from Sheet** (limit=30) → mevcut lead'leri Instantly'ye ekle
3. GitHub Actions → **Daily Pipeline** → yeni firmalar bul + ekle

---

## Yeni OSB Eklemek

Yeni bir şehir/OSB eklemek için:

1. `src/scraper/` altında yeni bir scraper dosyası oluştur (izmir_scraper.py'yi template olarak kullan)
2. `scripts/run_daily_pipeline.py` içinde import et ve `merge_sources([...])` listesine ekle

---

## GitHub Secrets (Gerekli)

| Secret | Açıklama |
|---|---|
| `ANTHROPIC_API_KEY` | Claude Haiku erişimi |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Google Sheets servis hesabı |
| `GOOGLE_SHEET_ID` | Hedef sheet ID |
| `INSTANTLY_API_KEY` | Instantly.ai API key |
| `INSTANTLY_CAMPAIGN_ID` | Aktif kampanya UUID |
| `APOLLO_API_KEY` | Email enrichment (Apollo) |
| `HUNTER_API_KEY` | Email enrichment (Hunter, fallback) |
| `TELEGRAM_BOT_TOKEN` | Bildirim botu |
| `TELEGRAM_CHAT_ID` | Hedef chat ID |
