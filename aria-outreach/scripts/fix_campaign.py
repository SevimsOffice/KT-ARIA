"""
One-shot script — hemen çalıştır, her şeyi düzelt:
  1. Gönderici hesapları kontrol et, paused olanları resume et
  2. Kampanyaya hesap listesi ata (email_list boşsa)
  3. daily_limit = 100 yap
  4. end_date < 60 gün kaldıysa 180 gün uzat
  5. Kampanyayı aktive et (completed/paused/stopped/draft → active)
  6. Kaç lead var, yoksa resend_from_sheet çalıştır uyarısı ver

Run via GitHub Actions:
  Actions → "Fix Instantly Campaign" → Run workflow

Or locally:
  python scripts/fix_campaign.py
"""

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from src.config import get_config
from src.outreach.instantly_client import InstantlyClient


def fix_campaign():
    cfg = get_config()
    client = InstantlyClient(cfg.instantly_api_key, cfg.instantly_campaign_id)

    print("=" * 60)
    print("ARIA — Instantly Campaign Fix")
    print("=" * 60)

    # ── Adım A: Gönderici hesaplar ──────────────────────────────────────
    print("\n── Adım A: Gönderici hesaplar ──")
    ACCOUNT_STATUS = {1: "✅ AKTİF", 2: "⛔ PAUSED", -1: "❌ bağlantı hatası", -2: "⚠️  soft bounce", -3: "❌ gönderim hatası"}
    accounts = client.list_accounts_v2()
    active_emails = []
    if not accounts:
        print("❌ Hiç gönderici hesap bulunamadı!")
        print("   → Instantly dashboard → Email Accounts → Gmail/Outlook hesabı ekle")
        print("   → Hesap eklendikten sonra bu scripti tekrar çalıştır")
    else:
        for acc in accounts:
            email  = acc.get("email", acc.get("username", "?"))
            status = acc.get("status", -99)
            label  = ACCOUNT_STATUS.get(status, f"bilinmiyor({status})")
            print(f"  {email}: {label}")
            if status == 1:
                active_emails.append(email)
            elif status == 2:
                print(f"  → Paused hesap resume ediliyor: {email}")
                ok = client.resume_account(email)
                if ok:
                    print(f"     ✅ Resume başarılı")
                    active_emails.append(email)
                else:
                    print(f"     ❌ Resume başarısız — Instantly UI'dan yeniden Gmail bağla")
            elif status == -1:
                print(f"     ❌ Bağlantı hatası — Instantly UI'dan Gmail'i yeniden yetkilendir")
        if not active_emails:
            print("\n❌ Aktif gönderici hesap yok — mail gönderilemez!")
            print("   → Instantly dashboard → Email Accounts → hesabı yeniden bağla")

    # ── Adım B-D: Kampanya bilgisi al ───────────────────────────────────
    print("\n── Kampanya durumu kontrol ediliyor... ──")
    info = client.get_campaign_status()

    if not info.get("found"):
        print(f"❌ Kampanya bulunamadı (status={info.get('status')})")
        print(f"   Campaign ID: {cfg.instantly_campaign_id}")
        sys.exit(1)

    name         = info.get("name", "?")
    status       = info.get("status", "?")
    allow_risky  = info.get("allow_risky_contacts", "?")
    end_date_str = info.get("end_date", "")
    daily_limit  = info.get("daily_limit", "?")
    email_list   = info.get("email_list", [])

    print(f"\nKampanya: '{name}'")
    print(f"  Durum          : {status}")
    print(f"  allow_risky    : {allow_risky}")
    print(f"  end_date       : {end_date_str or '(yok)'}")
    print(f"  daily_limit    : {daily_limit}")
    print(f"  email_list     : {email_list or '(boş)'}")

    patches = {}

    print(f"\n✅ allow_risky_contacts={allow_risky} (korunuyor — tahmin emailler gönderilmiyor)")

    # Fix: daily_limit
    if daily_limit != 100:
        patches["daily_limit"] = 100
        print(f"\n⚠️  daily_limit={daily_limit} → 100'ye çekiliyor")
    else:
        print("\n✅ daily_limit zaten 100")

    # Fix: end_date
    if end_date_str:
        try:
            end = date.fromisoformat(end_date_str)
            days_left = (end - date.today()).days
            if days_left < 60:
                new_end = (date.today() + timedelta(days=180)).isoformat()
                patches["end_date"] = new_end
                print(f"\n⚠️  Kampanya {days_left} gün sonra bitiyor ({end_date_str})")
                print(f"   → Uzatılıyor: end_date={new_end}")
            else:
                print(f"\n✅ end_date OK ({days_left} gün kaldı)")
        except ValueError:
            print(f"\n⚠️  end_date parse edilemedi: {end_date_str}")
    else:
        print("\nℹ️  end_date belirtilmemiş (süresiz)")

    # Fix: email_list boşsa aktif hesapları ata
    if not email_list and active_emails:
        patches["email_list"] = active_emails
        print(f"\n⚠️  Kampanyaya hesap atanmamış → {active_emails} atanıyor")

    # Apply setting patches
    if patches:
        print(f"\nUygulanan ayar düzeltmeleri: {patches}")
        ok = client.patch_campaign(patches)
        if ok:
            print("✅ Kampanya ayarları başarıyla güncellendi!")
        else:
            print("❌ Kampanya ayarları güncellenemedi — Instantly API hatası")
    else:
        print("\n✅ Ayar düzeltmesi gerekmedi")

    # Aktivasyon (completed dahil tüm non-active durumlar)
    if status != "active":
        print(f"\n⚠️  Kampanya durumu='{status}' → aktive ediliyor")
        ok = client.activate_campaign()
        if ok:
            print("✅ Kampanya aktive edildi!")
        else:
            print("❌ Aktivasyon başarısız — Instantly UI'dan 'Launch' / 'Resume' butonuna bas")
    else:
        print(f"\n✅ Kampanya durumu zaten aktif")

    # Final: lead sayısı kontrol
    print("\n── Lead sayısı kontrol ediliyor... ──")
    leads = client.get_leads_count()
    print(f"  Kampanyada mevcut lead sayısı: {leads}")
    if leads == 0:
        print("\n⚠️  Kampanyada hiç lead yok! Mail gönderilemez.")
        print("   → GitHub Actions → 'Resend from Sheet' workflow'unu çalıştır (limit=30)")
        print("   → Veya daily_pipeline workflow'unu çalıştır (yeni firmalar bulunur)")

    print("\n" + "=" * 60)
    print("İşlem tamamlandı.")
    if leads > 0:
        print("✅ Kampanya lead'li ve aktif — yarın maillar gitmeye başlar.")
    else:
        print("⚠️  Lead ekledikten sonra maillar gitmeye başlar.")
    print("=" * 60)


if __name__ == "__main__":
    fix_campaign()
