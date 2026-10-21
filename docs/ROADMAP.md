# FenerHub Yol Haritası

> **Durum (21 Ekim 2026): proje kapatıldı.** Aşama 1, 2, 3, 5, 6, 7 ve 10 tamam. İşaretsiz kalan maddeler
> **gelecek planıdır**; ayrıntılar en alttaki "Proje durumu" bölümünde.

## Çalışma kuralları (her aşama için geçerli)
- Aşamalar sırayla yapılır. Bir aşamaya başlamadan önce kodu incele, kısa bir plan sun ve onayımı bekle.
- Her aşama için ayrı bir branch aç (feat/..., fix/..., chore/...). İş bitince yerelde test et, neye bakmam gerektiğini yaz, onaydan sonra main'e merge et ve push yap. Render main'den otomatik deploy ediyor.
- Commit'ler küçük ve anlamlı olsun (feat:, fix:, refactor:, docs:, test:, chore:).
- seed.py'yi ASLA çalıştırma. Şema değişirken mevcut veri silinmesin.
- API anahtarı ve gizli bilgiler sadece backend'de ve ortam değişkenlerinde kalsın. Frontend'e, loglara veya git'e yazılmasın.
- SportsAPI istek bütçesi: Toplam günlük kullanım planın %60'ını geçmesin. Her yeni çekme işleminin önbellek süresini ve günlük istek maliyetini kodda yorum olarak yaz. 429 gelirse o özelliği o gün durdur, eski veriyle devam et.
- api.js, forum.js ve matchEngine.js'in çalışan kısımlarını bozma. Class veya id değiştirirsen JS'teki karşılığını da güncelle.
- Her yeni arayüz parçası 380px'te düzgün görünsün, kontrastı WCAG AA'yı geçsin ve prefers-reduced-motion'a uysun.
- Bir aşama bitince bu dosyadaki kutucuğu [x] yap ve altına bir satırlık not ekle (ne yapıldı, Render/Vercel'de değişen ayar).
- Render, Vercel veya başka bir serviste benim yapmam gereken bir ayar varsa adım adım yaz.
- Dokümantasyon: https://docs.sportsapipro.com/llms.txt

## Aşama 1: Acil hata, gerçek kullanıcı IP'si
- [x] Render proxy arkasında çalıştığı için request.client.host tüm kullanıcılarda aynı IP'yi döndürüyor olabilir. Bu durumda forumdaki "4 saniye bekle" kontrolü herkesi birlikte kilitliyor. Doğrula.
  - Doğrulandı (Render log): XFF = [kullanıcı, Cloudflare 104.23/172.70, Render iç 10.19x]. client_ip sağdan özel + Cloudflare'i atlayıp kullanıcıyı buluyor. Teşhis logu Aşama 2'de kaldırıldı.
- [x] uvicorn'u --proxy-headers --forwarded-allow-ips="*" ile başlat (Render start komutunda değişmesi gerekiyorsa söyle) ya da X-Forwarded-For'u güvenli şekilde oku.
  - `app/net.py client_ip()`: XFF sağdan okunur, özel ağ + Cloudflare atlanır (`*` en soldakini aldığı için sahtelenebilirdi). Render'da ayar değişmedi.
- [x] last_post sözlüğü sonsuza kadar büyümesin, eski kayıtlar temizlensin.
  - Dakikada bir 60 sn'den eski kayıtlar silinir, 10.000 üst sınır. Testler: `backend/tests/test_client_ip.py` (`python -m pytest`).

## Aşama 2: Kalıcı veritabanı (PostgreSQL)
- [x] SQLite Render'da her deploy'da siliniyor. Ücretsiz bir Postgres'e geç (Neon ya da Supabase, hangisini önerdiğini gerekçesiyle söyle). Hesabı ben açacağım, adım adım yaz.
  - Not: Neon seçildi (uyumayan ücretsiz plan, Frankfurt). Render Environment'a DATABASE_URL (pooler adresi) ve SPORTS_API_KEY eklendi.
- [x] DATABASE_URL varsa Postgres, yoksa yerelde SQLite kullanılsın.
  - Not: app/database.py, psycopg 3 + pool_pre_ping. Render'da SQLite'a düşerse log'a UYARI yazılır.
- [x] Forum (şu an ayrı forum.db ve ham sqlite3) da aynı veritabanına ve SQLAlchemy'ye taşınsın.
  - Not: posts tablosu (ForumPost), API alanları aynı kaldı; testler tests/test_forum.py.
- [x] Şema değişiklikleri için Alembic migration'ları kur.
  - Not: 0001 baseline + 0002 posts; açılışta run_migrations() mevcut tabloyu stamp'leyip upgrade eder (Render'da shell gerekmez).
- [x] Yereldeki mevcut verileri (forum mesajları, elle girilen sakatlıklar) yeni veritabanına aktaran tek seferlik bir script yaz.
  - Not: scripts/migrate_to_postgres.py çalıştırıldı: tüm tablolar + 14 forum mesajı (yerel + canlı site birleştirildi) Neon'a aktarıldı.

## Aşama 3: Canlı maç ve otomatik sakatlıklar
Önce bana SportsAPI planımı (Free/Pro/Ultra) ve Render'ın ücretsiz olup olmadığını sor.
- [x] Keşif: Son biten maç için /match/{id}/lineups (missingPlayers), /incidents, /statistics ve V6 /search?q=Fenerbahce + /team/{id}/injuries yapılarını en fazla 8 istekle incele, özetle.
  - 3 istek (injuries, shotmap, best-players); lineups/incidents/statistics önbellekten. missingPlayers isim + description + expectedEndDate veriyor; V6 injuries'te oyuncu adı boş (sadece V6 id). WS snapshot'ları REST ile aynı yapıda. 20 Ekim Slavia maçı WS kaydı için scripts/probe_ws_record.py hazır.
- [x] Canlı maç SportsAPI WebSocket'ten (wss://api.sportsapipro.com/v2/football/ws, kotadan sayılmıyor) alınsın. Bağlantıyı backend kursun, API anahtarı tarayıcıya gitmesin. Fenerbahçe maçı başlamadan 15 dakika önce abone olsun, bitince kapatsın. Koparsa artan beklemeyle yeniden bağlansın, hiç çalışmazsa 60 saniyelik REST yedeği devreye girsin.
  - app/live.py. 20 Ekim Slavia maçında canlı doğrulandı. match kanalı alanları noktalı düz anahtar ve kısmi geliyor ("status.code": 31); unflatten + kısmi güncelleme ile devre arası/ikinci yarı/maç sonu anında işleniyor (testi gerçek mesaj dizisiyle).
- [x] Veri sitenin kendi WebSocket kanalından (/ws/live) frontend'e aktarılsın.
  - state/update/goal/source mesajları; simülasyon bağlanıyor, bağlantı yoksa 20 sn REST yedeği.
- [x] Frontend: anlık skor ve dakika, gol animasyonu ve bildirimi (toast), olay akışı (gol/kart/değişiklik/VAR), gerçek maç istatistikleri, gerçek olaylara tepki veren 2D simülasyon.
  - Simülasyonda gerçek kadro, gol/kart/değişiklik/VAR/penaltı animasyonu ve bandı, canlı anlatıcı (Aşama 11 ile). Maçta doğrulandı; sadece devre arasında saatin 45+ diye ilerlemesi sorunu vardı, düzeltildi (backend anında devre arası + frontend uzatma sınırı).
- [x] Maç bitince /graph, /shotmap ve /best-players bir kez çekilip kaydedilsin, maç özeti olarak gösterilsin.
  - auto_sync.summary_targets/fetch_summary: başlamadan 2 sa 15 dk sonra, 2 güne kadar, kota ≥ 43 iken bir kez (3 istek). /detail -> summary, /api/matches -> has_summary. Simülasyonda "Maç özeti" sekmesi (frontend/js/summary.js): xG/şut özeti, SVG şut haritası, baskı grafiği (gol işaretli), en iyi 5 oyuncu; fikstürde oynanmış maçta düğme.
- [x] Maç günü eksikleri /lineups içindeki missingPlayers'tan otomatik gelsin (maça 24 saatten az kala 3 saatte bir, son 2 saatte 30 dakikada bir).
  - app/absences_sync.py; REST (auto_sync.lineups_every) ve maç sırasında WS lineups kanalından. Açıklamalar Türkçeye çevrilir, dönüş tarihi "10 Aralık" biçiminde.
- [x] Genel sakatlık raporu V6 injuries'ten günde 2 kez gelsin, isimler kadroyla eşleştirilsin, eşleşmeyenler loglansın.
  - V6 listesinde ad boş gelir; ad /v6/football/player/{id} ile oyuncu ilk görüldüğünde bir kez sorulup kalıcı saklanır (çalışma başına en fazla 5 yeni oyuncu). Genel rapor = en yeni kadro verisi + V6 (aynı oyuncuda kadro verisi kazanır). absences_sync.apply_v6_injuries, auto_sync'te 12 saatte bir, kota > 45 iken.
- [x] Sakatlık kayıtlarında source alanı olsun (api / manual). Otomatik güncelleme elle girilenleri silmesin.
  - Alembic 0004; mevcut kayıtlar manual. Aynı oyuncu için elle kayıt varsa otomatik kayıt eklenmez. Testler: tests/test_absences_sync.py.
- [x] Demo modu: ?demo=live ile geçmiş bir maçın olayları sırayla yeniden oynatılsın.
  - 20 Ekim Slavia maçının WS kaydı scripts/build_demo.py ile /ws/live biçiminde 233 KB'lık frontend/demo/*.json'a çevrildi; frontend/js/demo.js ×10/×20/×60 hızla oynatır (canlı akışla aynı işleyiş). Altbilgide ve README'de bağlantı.
- [x] Render ücretsizse maç saatinde sunucunun uyanık olması için bir çözüm öner. Ücretsiz planın kurallarına aykırı yöntem kullanma.
  - Seçilen: cron-job.org (ücretsiz), her gün 17:00-01:00 TSİ arası 10 dk'da bir /api/health. Kullanıcı kuracak. Ayrıca maç saatine yakın değilken backend veritabanını yarım saatte bir okur (auto_sync.snapshot/is_busy, live.near_match), Neon boşta uyuyabilir.

## Aşama 4: Görseller ve maç öncesi bilgiler
- [ ] Takım logoları (/api/teams/{id}/image) ve oyuncu fotoğrafları (/api/players/{id}/image) bir kez çekilsin, URL'leri veritabanında tutulsun. Her sayfa açılışında API'ye istek gitmesin. Yüklenemeyen görselde mevcut avatar gösterilsin.
  - Gelecek planı: indirme aracı hazır (backend/scripts/download_images.py, öncelik sırası: sıradaki rakipler, kadro, geçmiş rakipler; günde en fazla 15 istek). Görseller statik dosya olarak repoya girer. Bekleyen ~63 görsel indirilene kadar sitede baş harfli yedek logo/avatar görünüyor.
- [x] Sıradaki maç kartı: V6 /match/{id}/h2h ile son 5 karşılaşma ve iki takımın son 5 maç formu. Ligdeki sıralar mevcut puan durumundan alınsın. Günde bir kez çek.
  - V2 /match/{id}/h2h (son karşılaşmaların G/B/M sayısı; tek tek liste ucu yok, h2h/events 404) + /match/{id}/pregame-form (iki takımın ligdeki son 5 maçı, eskiden yeniye). Sıradaki maç 7 gün içindeyse günde bir kez, 2 istek. Sıralar kendi puan durumumuzdan. Ana kartta "Son N karşılaşma" çubuğu ve iki takımın lig formu.

## Aşama 5: Skor tahmin oyunu (12. Adam)
- [x] Kullanıcı kimliği: hesap açtırmadan, cihazda saklanan anonim kimlik + takma ad (forumdaki owner mantığıyla uyumlu). İleride giriş eklenebilecek şekilde tasarla.
  - Forumla ortak fhOwner + fhNick; sunucuda anahtarın özeti (predictions.player) saklanır, ileride bir hesaba bağlanabilir. Takma ad küfür filtresinden geçer.
- [x] Her maç için skor tahmini, maç başlayınca kilitlensin.
  - POST /api/predict: başlamadan değiştirilebilir, başlama saatinde (sunucu saati) 409. 14 gün içindeki maçlar açık. Alembic 0007.
- [x] Puanlama: tam skor 5, doğru gol farkı 3, doğru sonuç 1 puan.
  - predictions.points_for; testli (parametrik).
- [x] Maç bitince puanlar otomatik hesaplansın. Sezonluk ve haftalık liderlik tablosu olsun.
  - predictions.settle auto_sync'te (istek atmaz). /api/predict/leaderboard?scope=season|week (son 7 gün); "Taraftarlar vs Model" satırı.
- [x] Aynı cihazdan/IP'den aşırı tahmin girişi sınırlansın.
  - Cihaz başına maç başı tek tahmin (güncellenir), IP başına saatte 30 istek.
- [x] Maçın oyuncusu oylaması: maç bitince 24 saat açık kalsın, taraftar oyu ile API puanı yan yana gösterilsin.
  - /api/motm: başlamadan 2-26 saat sonra açık, adaylar ilk 11 + oyuna girenler, kişi başı bir oy, yanında SportsAPI puanı ve API'nin seçimi.

## Aşama 6: Forum güvenliği ve moderasyon
- [x] Tüm kullanıcı metinleri ekrana düz metin olarak eklensin (textContent ya da güvenli escape). innerHTML ile kullanıcı verisi basılmasın (XSS).
  - Denetlendi: forum mesajı/takma ad/alıntı textContent ile, diğer innerHTML'ler sabit metin ya da esc(). Yerelde <img onerror>/<script> içeren mesajla doğrulandı (çalışmadı, düz metin). frontend/vercel.json: frame-ancestors, nosniff, Referrer/Permissions-Policy.
- [x] "Mesajı bildir" butonu. 3 farklı kullanıcıdan bildirim alan mesaj otomatik gizlensin.
  - POST /api/forum/posts/{id}/report; bildiren = IP özeti (IP saklanmaz), mesaj başına bir kez, kendi mesajı bildirilemez, saatte 20 sınırı. 3 farklı IP -> posts.hidden + WebSocket "hide". Alembic 0006.
- [x] Küfür filtresi ayrı bir dosyaya taşınsın, Türkçe karakter varyasyonlarını da yakalasın.
  - app/profanity.py: büyük/küçük harf, aksan, rakam (s1ktir), araya noktalama (s.i.k), harf tekrarı. Küçük ı ayrı harf (sıkıştırdık sansürlenmez); belirsiz kökler tam kelime (götür, sikke korunur). Testler: tests/test_profanity.py.
- [x] CORS sadece kendi alan adlarımla (Vercel, localhost) sınırlı kalsın.
  - İzinli kaynaklar: fenerhub.vercel.app ve localhost:5500; yöntemler GET/POST, başlık Content-Type.

## Aşama 7: PWA, takvim ve paylaşım
- [x] PWA: manifest.json, ikonlar, service worker. Statik dosyalar önbellekte olsun, API verisi her zaman ağdan gelsin. → manifest.webmanifest + sw.js (sayfa önce ağdan, statik dosyalar stale-while-revalidate, API/video/kareler hiç önbelleğe girmez), offline.html yedeği.
- [x] Gol bildirimi (Web Push): izin veren kullanıcıya site kapalıyken bile gol ve maç başlangıç bildirimi. VAPID anahtarları ortam değişkeninde. → app/push.py + js/push.js; başladı/gol/bitti, sadece bilinen push servisleri, tekrar gönderim engelli. Anahtar yoksa düğme gizli.
- [x] Takvime ekle: /api/calendar.ics ile fikstür takvim aboneliği, saat değişince takvim güncellensin. Fikstür bölümüne "Takvime ekle" butonu. → app/ical.py (UTC saat, 1 saat önce hatırlatma); iPhone/Google/Outlook bağlantıları.
- [x] Paylaşım önizlemesi (Open Graph / Twitter Card): başlık, açıklama ve sıradaki maçı gösteren görsel. Dinamik üretilemiyorsa sabit kapak görseli. → sabit kapak img/og.png (1280×640).
- [x] SEO: anlamlı title, meta description, lang="tr", favicon. → ayrıca canonical, theme-color, apple-touch-icon.
- [x] Footer notu: "Bu site Fenerbahçe SK ile resmi bir bağlantısı olmayan bir taraftar projesidir. Veriler SportsAPI Pro'dan alınmaktadır."

## Aşama 8: İçerik ve analiz (gelecek planı)
- [ ] Oyuncu detay paneli: tıklayınca açılsın. İçinde attribute-overviews radar grafiği, güçlü/zayıf yönler, sezon maç puanları grafiği ve transfer geçmişi olsun. Sadece tıklanınca çek, 24 saat önbellekte tut.
- [ ] Oyuncu karşılaştırma: iki oyuncu radar grafikte yan yana.
- [ ] Sezon istatistikleri sayfası: xG trendi, gol dakikası dağılımı (goal-distributions), iç saha/deplasman karşılaştırması.
- [ ] Süper Lig gol ve asist krallığı (top-players, günde bir kez).
- [ ] Rakip ön izleme: sıradaki rakibin formu, en golcüsü ve eksikleri.
- [ ] Fenerbahçe haberleri (V1 news, günde 2 kez): sadece başlık, görsel ve kaynağa link.
- [ ] Grafikler için hafif bir kütüphane kullan (önce bana sor) ya da SVG ile çiz.

## Aşama 9: Kalite, test ve izleme (kalanlar gelecek planı)
- [x] Backend için pytest testleri: puan durumu ayrıştırma, oyuncu istatistiği toplama, sakatlık eşleştirme, tahmin puanlama, forum doğrulamaları. API çağrıları mock'lansın.
  - 106 backend + 13 frontend testi; conftest her türlü HTTP isteğini engeller, testler geçici SQLite kullanır.
- [ ] GitHub Actions: her push ve PR'da lint (ruff) ve testler. README'ye durum rozeti.
  - Kısmen: .github/workflows/ci.yml testleri çalıştırıyor, ama GitHub hesabındaki ödeme kilidi yüzünden işler başlamıyor. Kilit kalkınca ruff ve rozet eklenecek.
- [ ] Sentry (ücretsiz plan): backend ve frontend hataları, DSN ortam değişkeninde.
- [ ] Yapılandırılmış loglama: istek kotası, sync süreleri, WebSocket bağlantı durumu.
- [ ] /api/health gerçek durumu döndürsün: veritabanı bağlantısı, son sync zamanı, kalan API kotası.
- [ ] Ziyaretçi analitiği: çerezsiz ve KVKK dostu (Umami ya da Plausible). Önerini söyle, hesabı ben açacağım.
- [ ] Lighthouse: performans, erişilebilirlik ve SEO 90'ın altındaysa iyileştir. 400 karelik arka plan animasyonunu özellikle kontrol et.

## Aşama 10: Portföy
- [x] README'yi güncelle: tüm özellikler, mimari diyagramı (Mermaid), ekran görüntüsü ve demo GIF'i için yer, kurulum, ortam değişkenleri tablosu, API uç noktaları, test komutu.
  - "Mühendislik açısından öne çıkanlar" bölümü, CI ve teknoloji rozetleri, 4 güncel ekran görüntüsü (docs/screenshots), İngilizce özet. Demo GIF'i henüz yok (canlı maç kaydından sonra eklenebilir).
- [x] docs/ altına kısa bir "Teknik kararlar" notu: neden WebSocket proxy, neden Postgres, istek bütçesi nasıl yönetildi.
  - docs/teknik-kararlar.md: 8 karar (sorun, çözüm, bedel) + test/CI. Ayrıca .github/workflows/ci.yml: her push'ta pytest ve node --test.
- [x] .env.example güncel olsun.
  - SPORTS_API_KEY ve DATABASE_URL (temizlik aşamasında eklendi); README'de ortam değişkenleri tablosu.

## Aşama 11: Akıllı içerik (ücretsiz, kalanlar gelecek planı)
Ücretli yapay zekâ API'si kullanılmaz. İçerik kural, şablon ve istatistik modeliyle üretilir; tamamen
ücretsiz ve uydurma yapmaz. (Önceki "Claude API" planı ücret nedeniyle değiştirildi; sohbet botu ve
günün tribün özeti çıkarıldı, forum moderasyonu Aşama 6'da kalıyor.)
Ortak kurallar:
- Rakamlar her zaman veritabanından gelir; şablon sadece cümleyi kurar. Aynı olaya her seferinde aynı
  kalıp gelmesin diye her durum için birden fazla cümle kalıbı olur.
- Üretilen metin bir kez üretilip veritabanında saklanır (maç başına), her sayfa açılışında yeniden üretilmez.
- Yeni API isteği gerekirse günlük bütçeye (%60) dahildir; mümkünse Aşama 3'te kaydedilen veriler kullanılır.
- Şablon ve model kodu birim testli (sabit girdiden beklenen metin/tahmin).

- [ ] Maç önü analizi (şablonlu): son 5 maç formu, aradaki son maçlar, eksikler, puan durumu farkı, ev/deplasman performansı. Maç günü bir kez üretilir, maç kartında "Maç önü" sekmesi.
- [ ] Maç sonu raporu (şablonlu): olaylar, istatistikler (topla oynama, şut, xG), şut haritası ve oyuncu puanlarından paragraflar ("İlk yarıda baskılı başlayan Fenerbahçe…"). Maç bitince bir kez üretilir (Aşama 3'teki maç özeti verisiyle).
- [x] Canlı maç anlatıcısı: her olay türü (gol, kart, ikinci sarı, değişiklik, VAR, penaltı, devre, maç sonu) için 10-15 spiker cümlesi kalıbı; oyuncu adı, dakika ve skor eklenir. `/ws/live` ile simülasyon bandına ve alt satıra gider.
  - frontend/js/commentary.js (13 olay grubu, ana gruplarda 10-12 kalıp, cümle olay kimliğinden seçilir); simülasyonda alt satır + anlatım akışı. Testler: frontend/tests/commentary.test.cjs.
- [x] İstatistik modeliyle tahmin rakibi: takımların attığı/yediği gol ortalamasından (ev/deplasman ayrı) Poisson modeli ile skor ve sonuç olasılıkları (%G / %B / %M). Maç başlamadan kilitlenir; Aşama 5'teki tahmin oyununda "Taraftarlar vs Model" tablosu. Modelin nasıl çalıştığı sitede kısaca anlatılır.
  - app/model.py (Poisson, puan durumundaki gollerden hücum/savunma gücü, saha etkisi, az maçta ortalamaya çekme). Model her maça başlamadan 24 saat içinde tahmin bırakır, liderlikte ayrı satır.
- [ ] Maçın oyuncusu kartı (şablonlu): Aşama 5'teki oylama bitince kazanana API puanı ve maç istatistikleriyle kısa tanıtım.
- [ ] İsteğe bağlı: ücretsiz kotası olan bir dil modeliyle (örn. Gemini/Groq) sadece maç raporu cümlelerine "cila". Sağlayıcıdan bağımsız arayüz; kota biterse, hata olursa ya da anahtar yoksa şablonlu metin gösterilir. Forum mesajı gibi kullanıcı verisi gönderilmez. Sağlayıcının güncel ücretsiz plan koşulları başlamadan önce kontrol edilir.

---

## Proje durumu (kapanış, 21 Ekim 2026)
Yeni oturumda bağlam kaybolmasın diye eklendi; yol haritası maddesi değildir.
- **Canlıda:** site https://fenerhub.vercel.app (Vercel), API https://fenerhub.onrender.com (Render ücretsiz, 15 dk trafiksiz uyur), veritabanı Neon Postgres. Render main'den otomatik deploy eder; şema migration'ları açılışta çalışır.
- **SportsAPI:** Free plan, 100 istek/gün, bütçe %60 = 60 istek/gün; kota 03:00 TSİ yenilenir. WebSocket kotasız; canlı maç oradan izlenir. Maç saatine yakın değilken backend veritabanını yarım saatte bir okur.
- **Ortam değişkenleri (Render):** SPORTS_API_KEY, DATABASE_URL, VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY (bildirim anahtarları yoksa bildirim düğmesi gizli kalır).
- **Elle yapılacaklar:** cron-job.org ile 17:00-01:00 TSİ arası 10 dk'da bir /api/health (maç saatinde sunucu uyanık kalsın); GitHub ödeme kilidini kaldırıp CI'yi açmak; görselleri günde 15'er indirmek (`python -m scripts.download_images --max 15 --keep 40`).
- **Gelecek planı (öncelik sırasıyla):** görsellerin tamamlanması (Aşama 4), maç önü/maç sonu şablonlu metinler ve maçın oyuncusu kartı (Aşama 11), oyuncu detay paneli ve sezon istatistikleri (Aşama 8), izleme: Sentry, /api/health'te gerçek durum, Lighthouse (Aşama 9).

## Temizlik yapıldı (20 Ekim 2026, chore/cleanup)
- Deneme scriptleri ve ham API çıktıları silindi; pycache, editör ayarı ve dosya önbellekleri git'ten çıkarıldı (yerelde duruyor). Tek kök `.gitignore`, `backend/.env.example`, README, MIT LICENSE eklendi.
- Taşınanlar: `backend/sync.py` → `backend/app/sync.py` (`python -m app.sync`); `add_absence.py`, `download_logos.py`, `seed.py` → `backend/scripts/` (`python -m scripts.<ad>`); `frontend/extract.py` → `tools/extract.py`. Yukarıdaki notlarda geçen eski yollar bu yeni yerleri gösterir.
- Render ve Vercel ayarları değişmedi.
