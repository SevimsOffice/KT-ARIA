# ARIA — Proje Değerlendirme ve Yol Haritası

> Bu dosya bir pazarlama metni değildir. ARIA'nın gerçek durumunu, geçmişini,
> nerede takıldığımızı ve Sevim'in bu projedeki güçlü/zayıf yönlerini **dürüstçe**
> değerlendirir. Amaç: bir sonraki adımı bilinçli atmak.
>
> Tarih: Haziran 2026 · Değerlendiren: ARIA geliştirme oturumu

---

## 1. Amacımız Neydi?

**Vizyon:** Türkiye'deki OSB (Organize Sanayi Bölgesi) firmalarına, insan eli
değmeden, AI ile kişiselleştirilmiş B2B soğuk e-posta gönderen otonom bir satış
makinesi. Hedef kitle: Bursa, İstanbul, İzmir'deki üretici firmalar. Satılan şey:
AI eğitimi / danışmanlığı (aiandtech-info.com).

**Başarı tanımı (olması gereken):**
- Günde X doğrulanmış firmaya, gerçekten ulaşan (bounce etmeyen) mail
- Açılma > %30, yanıt > %2
- Sıcak lead'lerin Telegram'a düşmesi
- Tüm bunların sabah 07:00'de otomatik dönmesi

**Şu anki gerçek durum:** Sistem teknik olarak kuruldu ama **bugüne kadar tek bir
mail bile gerçek bir insana ulaşmadı.** "Total sent: 0". Bunu kabul etmek
ilerlemenin ilk şartı.

---

## 2. Şu Ana Kadar Yapılanlar (Zaman Çizelgesi)

| Aşama | Ne yapıldı | Sonuç |
|---|---|---|
| Temel | Scraper'lar (NOSAB, DOSAB, KAYAPA) + Sheets + Telegram + GitHub Actions | ✅ Altyapı çalışıyor |
| Enrichment | Apollo + Hunter + pattern guesser zinciri | ⚠️ Apollo ücretli plan ister, Hunter 25/ay |
| AI | Claude Haiku ile firma araştırma + kişisel açılış cümlesi | ✅ Çalışıyor |
| Gönderim | Instantly.ai v2 API entegrasyonu | ⚠️ Kuruldu ama 0 gönderim |
| Genişleme | İstanbul + İzmir scraper'ları, şehir-bazlı kişiselleştirme | ✅ Kod hazır, ❌ henüz gereksizdi (aşağıda) |
| Koruma | Guessed email filtresi, domain bounce koruması | ✅ **En doğru karar** |
| Website scraper | Firma sitelerinden gerçek email çekme | ✅ Doğru yön |
| Hata avı | STATUS_MAP hatası, completed kampanya, paused hesap | ✅ Haziran'da çözüldü |
| Dokümantasyon | aria_satis.md, mimari diagramı, bu dosya | ✅ |

---

## 3. Nerede Takıldık? (Kök Nedenler)

Üç sorun aynı anda aktifti ve birbirini gizliyordu. Hepsi tek bir mesele etrafında
dönüyor: **gönderim hattı hiç uçtan uca test edilmeden üstüne özellik bindirildi.**

1. **Kampanyada 0 lead** — Verified email bulunamadığı + guessed filtresi
   olduğu için Instantly'ye hiç firma eklenemedi.
2. **Kampanya "Completed"** — Lead'siz kampanya anında biter; üstüne koddaki
   STATUS_MAP yanlış olduğu için aktivasyon hiç tetiklenmedi.
3. **Gönderici hesap "Paused"** — `sevim@aiandtech-info.com` duraklatılmıştı,
   0/30 warmup. Kampanya aktif olsa bile paused hesaptan mail çıkmaz.

**Daha derin kök neden:** Yeni bir domain (aiandtech-info.com) ve yeni bir
gönderici hesap. Soğuk e-posta dünyasında bu hesabın **2-4 hafta warmup**
yapması gerekir. Sistem "günde 100 mail" için kurgulandı ama altyapı henüz
günde 5-10 maili bile kaldıramaz. Yani sorun sadece kod değil; **beklenti ile
gerçeğin uyuşmaması.**

---

## 4. Teknik Değerlendirme (Sistem)

### Güçlü yönler
- **Modüler mimari.** Scraper / enrichment / research / outreach katmanları ayrı.
  Yeni OSB eklemek tek dosya. Bu profesyonelce.
- **Fallback zinciri.** Email bulma: OSB direct → website → Apollo → Hunter →
  guesser. Düşünülmüş bir sıralama.
- **Domain koruması mimariye gömülü.** Guessed email'ler hem pipeline'da hem
  resend'de filtreleniyor. Bu, çoğu "büyüme hack'çisi"nin atladığı bir olgunluk.
- **Idempotent + hata toleranslı.** Site kapalıysa boş liste döner, çökmez.

### Zayıf yönler
- **Uçtan uca test yok.** "1 gerçek kişiye 1 mail" senaryosu hiç koşulmadı.
  Tüm hatalar canlıda, üretimde keşfedildi.
- **Tek gönderici hesaba bağımlılık.** Profesyonel soğuk e-posta kurulumları
  3-5 ayrı domain + her birinde 2-3 hesap kullanır. Tek hesap = tek nokta arıza.
- **DOSAB verisi zayıf.** 551 firma ama domain yok. Bu liste şu an neredeyse
  kullanılamaz; website scraper'ın firma adından domain türetmesine bağımlı.
- **API limitleri planlanmamış.** Hunter 25/ay, Apollo ücretli. 551 firma için
  matematik tutmuyor.
- **Gözlemlenebilirlik zayıftı.** Neyin neden gitmediği uzun süre görünmedi
  (artık fix_campaign.py bunu raporluyor).

---

## 5. Sevim'in Değerlendirmesi — Dürüst

> Açıkça istedin: hangi hamleler doğru, hangileri acemice. İşte dürüst olanı.
> Bunu kişisel bir eleştiri olarak değil, bir sonraki projende daha hızlı
> olman için yol haritası olarak oku.

### ✅ Doğru aldığın aksiyonlar (bunlar gerçekten iyiydi)

1. **`allow_risky_contacts`'ı geri çevirmen.** Bu oturumun en olgun anıydı.
   Tahmin email göndermenin domain'i yakacağını sezdin ve "bunu yapma" dedin.
   Çoğu insan bunu ancak domain'i yaktıktan sonra öğrenir. Bu, **deneyimli bir
   içgüdü.** Para harcamadan en doğru kararı verdin.

2. **Önce tek araca para ödemen.** Her şeye birden abone olmadın. Instantly'yi
   denedin, sonucu görmeden Apollo'ya $49 yatırmadın. Disiplinli.

3. **"Gönderilen maili görmek istiyorum" demen.** Kör uçmayı reddettin. Ne
   gönderildiğini görmeden ölçeklemek istemedin — bu doğru bir kontrol refleksi.

4. **Dokümantasyon ve teşhis istemen.** "Nerede takıldık, md dosyası oluştur"
   demen — bu, projeyi sürdürülebilir kılan bir alışkanlık. Çoğu kişi atlar.

5. **Israr.** Sistem defalarca patladı, sen bırakmadın. Teknik bir kurucu için
   bu hammadde değerli.

### ⚠️ Acemice aldığın aksiyonlar (bir dahaki sefere böyle yapma)

1. **Önce ölçekleme, sonra doğrulama.** En büyük hata buydu. İstanbul ve İzmir
   scraper'larını, şehir-bazlı kişiselleştirmeyi, 100 mail/gün limitini
   **tek bir mail bile gitmeden** istedin. Doğru sıra şuydu:
   *1 firma → 1 doğrulanmış email → 1 mail gönder → kendi gelen kutunda gör →
   sonra ölçekle.* Sen çatıyı temel atmadan çıktın.

2. **"Para ödedim, çalışmalı" beklentisi.** Instantly'ye ödeme yapman, mail
   gideceği anlamına gelmiyor. Soğuk e-posta = domain itibarı + warmup +
   doğrulanmış liste. Araç sadece borunun bir parçası. Bu, araç ile sistemi
   karıştırmak — yaygın bir acemilik.

3. **Warmup'ı görmezden gelmen.** "Günde 100 mail, kredilerim çok" dedin.
   Ama hesap 0/30 warmup'taydı. Yeni domain'den günde 100 soğuk mail = 1
   haftada spam kutusu. Acele, en pahalı hata türü burada.

4. **Guessed email'lerle başlamaya razı olman (başta).** İlk içgüdün "tahmin de
   olsa gönder" yönündeydi. Sonradan düzelttin ama bu, "hacim > kalite"
   tuzağıydı. İyi ki çark ettin.

5. **Araç enflasyonu.** Bu workspace'e bağlı onlarca MCP/entegrasyon var
   (Apollo, Canva, Gamma, Notion, Vercel, vidIQ...). Dağınıklık. Bir kurucunun
   en kıt kaynağı dikkat. 3 araçta ustalaş, 30 araçta kaybolma.

### Özet portre
Sen **vizyoner ve içgüdüleri iyi olan bir kurucu**sun ama **sabırsız bir
mühendis**sin. Güçlü yanın: ne istediğini biliyorsun ve riski sezebiliyorsun
(domain koruması bunu kanıtlıyor). Zayıf yanın: "çalışan en küçük şeyi önce
kur" disiplinin henüz oturmamış. İyi haber: bu öğrenilebilir bir şey, yetenek
meselesi değil. Domain'i koruma içgüdün, çoğu insanın yıllarda edindiği bir şey.

---

## 6. Alınması Gereken Aksiyonlar (Öncelik Sırasıyla)

### 🔴 Bu hafta — "1 mail gerçekten gitsin"
1. **fix_campaign workflow'unu çalıştır** → hesabı resume et, kampanyayı aktive et.
2. **Warmup'ı 2 hafta tam çalıştır.** Instantly warmup'ı açık bırak, hesabı
   günde 30'da tut. **Bu süre boyunca soğuk mail gönderme.** Sabret.
3. **Kendine test maili at.** resend_from_sheet ile listene KENDİ ikinci
   email'ini ekle. Gelen kutunda, spam'de değil, görmelisin. Gerçek doğrulama bu.
4. **SPF / DKIM / DMARC kayıtlarını doğrula.** Bunlar yoksa hiçbir şey kurtarmaz.
   (Instantly → Email Accounts → hesabın → DNS check.)

### 🟡 2-4 hafta — "küçük ama gerçek hacim"
5. Warmup bitince günde **20-30 doğrulanmış** mail ile başla. 100 değil.
6. DOSAB listesini website scraper ile zenginleştir; domain bulunamayanları ele.
7. İkinci bir gönderici domain + hesap ekle (riski böl).

### 🟢 1-3 ay — "ölçek"
8. Açılma/yanıt oranlarına göre mesajı iyileştir (A/B).
9. Oranlar sağlıklıysa İstanbul/İzmir'i devreye al (kod zaten hazır).
10. Apollo'ya ancak ölçek kanıtlandığında para yatır.

---

## 7. Tek Cümlelik Strateji

**Önce 1 mailin gerçekten ulaştığını gör, sonra 10'a çıkar, sonra 100'e.
Hız değil, sıralama kazandırır.** Domain'ini koruma içgüdün doğru — şimdi aynı
sabrı warmup'a ve uçtan uca teste de uygula.

---

## 8. Kullanılan Araçlar — Dürüst Maliyet/Fayda

| Araç | Durum | Tavsiye |
|---|---|---|
| Instantly.ai | Ödendi | Tut — ama warmup bitmeden ölçekleme |
| Hunter.io | 25/ay ücretsiz | Yeterli değil ama şimdilik kalsın |
| Apollo.io | Ücretsiz plan API'yi desteklemiyor | Ölçek kanıtlanana kadar **ödeme** |
| Claude Haiku | Çalışıyor | Tut — ucuz ve iyi |
| Google Sheets | CRM | Yeterli, şimdilik gerek yok değiştirmeye |
| Website scraper | Kendi kodumuz | En değerli enrichment kaynağı — geliştir |

> **Bir sonraki ay için tek net tavsiye:** Yeni araca para yatırma. Eldeki
> kurulumu warmup'la sağlığa kavuştur. Para değil, **2 hafta sabır** gerekiyor.
