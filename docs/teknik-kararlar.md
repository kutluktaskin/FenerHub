# Teknik kararlar

FenerHub'ı geliştirirken verdiğim önemli kararlar ve nedenleri. Her başlıkta önce sorun, sonra
seçtiğim çözüm ve bedeli var.

## 1. Günde 100 istekle canlı bir maç sitesi

**Sorun:** SportsAPI Pro'nun ücretsiz planı günde 100 istek veriyor. İlk sürüm bir maçı izlemek için
REST'le 5 dakikada bir olay, 15 dakikada bir istatistik çekiyordu: tek bir maç ~60 istek. Ayrıca
Render'ın ücretsiz sunucusu 15 dakika trafik olmazsa uyuyor ve disk kalıcı değil; her uyanışta
önbellek dosyaları siliniyor, aynı veri yeniden çekiliyordu.

**Çözüm:**
- **Bütçe kuralı:** günlük kullanım planın %60'ını (60 istek) geçmez. Her istekte API'nin bildirdiği
  kalan kota loglanır ve kodda tutulur (`sync.quota_remaining`).
- **Önbellek veritabanında** (`api_cache` tablosu, `app/cache.py`): her cevap çekilme zamanıyla saklanır.
  Sunucu uyanınca ya da yeniden deploy edilince veri tekrar çekilmez.
- **İşe göre aralık** (`app/auto_sync.py`): maç listesi maç yokken 2 saatte bir, maç saatinde 8 dakikada
  bir; puan durumu 3 saatte bir; kadro maça 24 saat kala 3 saatte bir, son 2 saatte 30 dakikada bir.
- **Hata olunca eski veri korunur:** yenileme başarısız olursa önbellekteki sayfa silinmez
  (eskiden silindiği için sitedeki takım renkleri kayboluyordu; testi: `tests/test_page_cache.py`).

**Bedel:** veriler birkaç dakika gecikmeli olabilir. Canlı maç için bu kabul edilemezdi, bkz. 2.

## 2. Canlı maç: WebSocket proxy

**Sorun:** Maç sırasında saniyeler önemli, ama REST yoklaması hem yavaş hem kota yiyor.

**Çözüm:** SportsAPI'nin WebSocket'i kotadan düşmüyor. Backend (`app/live.py`) Fenerbahçe maçından
15 dakika önce bu WebSocket'e bağlanır, gelen olayları veritabanına yazar ve sitenin kendi
`/ws/live` kanalıyla tarayıcılara iletir.
- **API anahtarı tarayıcıya hiç gitmez.** Tarayıcı SportsAPI'ye değil, bizim sunucumuza bağlanır.
- Tek bir upstream bağlantı, sitedeki bütün izleyicilere yayılır (izleyici sayısı kotayı etkilemez).
- Koparsa 2, 4, 8 … 60 saniye bekleyerek yeniden bağlanır. 2 dakikadan uzun süre bağlanamazsa REST
  yedeği devreye girer; o da kalan kotaya bakar (55'in altında 5 dakikada bir, 40'ın altında durur).
- WebSocket maçı izlerken periyodik senkron o maç için REST isteği atmaz (`live.covers`).

**Bedel:** Render'ın ücretsiz sunucusu 15 dakika istek gelmezse uyur. Maç saatlerinde (17:00-01:00) ücretsiz
bir zamanlayıcı (cron-job.org) 10 dakikada bir sağlık ucunu çağırır; günün geri kalanında sunucu uyur.
Sunucu uyanıkken bile maç saatine yakın değilsek veritabanı yarım saatte bir okunur; maç takvimi
bellekte tutulur. Böylece Neon'un ücretsiz işlem süresi boşa harcanmaz.

## 3. SQLite'tan PostgreSQL'e (Neon)

**Sorun:** Render'ın ücretsiz diskinde SQLite her deploy'da sıfırlanıyordu: forum mesajları ve elle
girilen sakatlıklar kayboluyordu.

**Çözüm:** Ücretsiz Neon Postgres (Frankfurt; Render ile aynı bölge, düşük gecikme). `DATABASE_URL`
varsa Postgres, yoksa yerelde SQLite (`app/database.py`). Neon'un bağlantı havuzu (PgBouncer) nedeniyle
psycopg 3'te sunucu tarafı hazır sorgular kapalı (`prepare_threshold=None`) ve kopan bağlantılar için
`pool_pre_ping` açık. Mevcut veriler tek seferlik bir scriptle taşındı (`scripts/migrate_to_postgres.py`;
id'ler korunur, Postgres sayaçları yeniden ayarlanır, canlı forumdaki mesajlarla birleştirilir).

**Güvenlik kararı:** uygulama `.env`'deki `DATABASE_URL`'i kendisi okumaz. Yerelde yanlışlıkla canlı
veritabanına yazmamak için değişkenin kabukta açıkça verilmesi gerekir.

## 4. Komut satırı olmadan şema değişikliği (Alembic)

**Sorun:** Render'ın ücretsiz planında shell yok; `alembic upgrade` elle çalıştırılamaz. Ayrıca
Alembic'ten önce oluşturulmuş bir veritabanı vardı.

**Çözüm:** Migration'lar uygulama açılırken çalışır (`app/migrate.py`). Tablolar var ama
`alembic_version` yoksa veritabanı veriye dokunmadan ilk sürüm olarak işaretlenir (stamp), sonra yeni
migration'lar uygulanır. Boş veritabanında (yeni Neon) her şey sıfırdan kurulur.

## 5. Proxy arkasında gerçek kullanıcı IP'si

**Sorun:** Forumda aynı IP'den 4 saniyede bir mesaj sınırı var. Render ve Cloudflare proxy'lerinin
arkasında `request.client.host` herkes için aynı adresi döndürebilir; bu durumda tek kullanıcı herkesi
kilitler. `--forwarded-allow-ips="*"` ise başlığı en soldan okuduğu için kullanıcı tarafından
sahtelenebilir.

**Çözüm:** `X-Forwarded-For` sağdan okunur; özel ağ adresleri ve Cloudflare'in yayımladığı aralıklar
atlanır, ilk güvenilmeyen adres kullanıcıdır (`app/net.py`). Render log'unda doğrulandı:
`[kullanıcı, Cloudflare, Render iç ağı]`. Hız sınırı sözlüğü de sonsuza kadar büyümesin diye dakikada
bir temizlenir.

## 6. Simülasyon: dürüst temsil

**Sorun:** API oyuncuların sahadaki anlık konumunu vermiyor; sadece olaylar, istatistikler ve kadro var.

**Çözüm:** Gerçek olan her şey gerçek veriden: skor, dakika, kadro (forma numarası, isim), kartlar,
değişiklikler, goller, topla oynama oranı. Konumlar ve top akışı temsili; atak yönü gerçek topla oynama
oranına göre seçilir. Bu, sahanın altında açıkça yazılı. Olaylar sahada canlandırılır (gol, kart,
değişiklik, VAR) ve şablonlu bir anlatıcı spiker cümlesi kurar (`frontend/js/commentary.js`): isim,
dakika ve skor olaydan gelir, cümle olayın kimliğinden seçilir ki herkes aynı cümleyi görsün.

## 7. Ücretli yapay zekâ yerine şablon ve istatistik

**Karar:** Yapay zekâ ile maç raporu ve sohbet botu planlandı, ancak ücretli API'ler kullanılmadı.
Rapor ve anlatım şablonla, tahmin istatistik modeliyle (Poisson) yapılacak. Rakamlar her zaman
veritabanından gelir, uydurma yoktur, maliyet sıfırdır. Dil modeli ileride sadece isteğe bağlı bir
"metin cilası" olarak, şablona otomatik geri dönüşle eklenebilir.

## 8. Framework'süz frontend

**Karar:** Frontend React yerine vanilla JavaScript ve modern CSS ile yazıldı (container query'ler,
`:has()`, View Transitions, Popover API, `oklch` renkler). Proje küçük, derleme adımı yok, Vercel'de
statik dosya olarak sunuluyor. Dosyalara sürüm etiketi (`?v=`) eklenir ki tarayıcı eski JS ile yeni
CSS'i karıştırmasın.

**Bedel:** Bileşen yeniden kullanımı ve durum yönetimi elle yapılıyor; proje büyürse bir framework'e
geçmek mantıklı olur.

## Test ve CI

- Backend: pytest (geçici SQLite; gerçek veritabanına ve SportsAPI'ye dokunmaz). Canlı maç modülü
  sahte WebSocket mesajlarıyla, kota bütçesi, önbellek koruması ve sakatlık güncellemesi ayrı ayrı test edilir.
- Frontend: Node'un yerleşik test aracı (`node --test`), ek paket yok.
- GitHub Actions her push'ta ikisini de çalıştırır (`.github/workflows/ci.yml`).
