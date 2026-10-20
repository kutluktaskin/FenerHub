# Geliştirme rehberi

Yerelde çalıştırma, testler, araçlar, ortam değişkenleri, API ve klasör yapısı.

## Yerelde çalıştırma

Gerekenler: Python 3.12+, Node 18+ (sadece frontend testleri için), bir SportsAPI Pro anahtarı (ücretsiz plan yeterli).

```bash
cd backend
python -m venv venv
venv\Scripts\activate              # macOS/Linux: source venv/bin/activate
pip install -r requirements-dev.txt

copy .env.example .env             # macOS/Linux: cp .env.example .env
# .env içine SPORTS_API_KEY yazın; DATABASE_URL boş kalırsa yerel SQLite kullanılır

uvicorn app.main:app --reload --port 8000
```

Frontend'i ayrı bir terminalde statik olarak sunun. Site `localhost`'ta açılınca API olarak otomatik
`http://127.0.0.1:8000` kullanır:

```bash
cd frontend
python -m http.server 5500         # http://localhost:5500
```

## Testler

```bash
cd backend && python -m pytest                # backend (geçici SQLite, ağ isteği yok)
node --test "frontend/tests/*.test.cjs"       # frontend (kök klasörde, ek paket gerekmez)
```

GitHub Actions ikisini her push'ta çalıştırır: `.github/workflows/ci.yml`.

## Ortam değişkenleri

| Değişken | Açıklama |
|---|---|
| `SPORTS_API_KEY` | SportsAPI Pro anahtarı. Sadece backend'de; tarayıcıya gitmez. |
| `DATABASE_URL` | Postgres adresi (Neon pooled). Boşsa yerel SQLite. Uygulama bunu `.env`'den kendisi okumaz; yerelde Postgres'e bağlanmak için kabukta açıkça verin. |
| `RENDER` | Render'ın kendisi tanımlar; Render'da SQLite'a düşülürse log'a uyarı yazdırır. |

## Elle çalıştırılan araçlar (backend klasöründe)

| Komut | Ne yapar |
|---|---|
| `python -m app.sync` | Maçları, kadroyu, istatistikleri ve puan durumunu API'den çeker (`--offline`: sadece önbellek, istek atmaz) |
| `python -m scripts.add_absence liste` | Sakatlık ve ceza kayıtlarını listeler; `ekle` ve `sil` alt komutları da var |
| `python -m scripts.download_logos --dry-run` | Eksik takım logolarını sayar; parametresiz çalışınca indirir (her logo 1 istek) |
| `python -m scripts.migrate_to_postgres --dry-run` | Yerel SQLite verisini Postgres'e aktarır (tek seferlik) |
| `python -m scripts.seed` | **Veritabanını siler** ve eski örnek verileri yükler; onay ister, canlıda kullanılmaz |

## API uç noktaları

Canlı ve etkileşimli doküman: https://fenerhub.onrender.com/docs

| Yöntem | Yol | Açıklama |
|---|---|---|
| GET | `/api/health` | Sağlık kontrolü |
| GET | `/api/matches` | Sezonun bütün maçları (`?competition=super_lig\|uefa`) |
| GET | `/api/matches/upcoming` | Sıradaki maçlar ve maç günü eksikleri |
| GET | `/api/matches/{id}` | Tek maç |
| GET | `/api/matches/{id}/detail` | Olaylar, istatistikler, kadrolar (önbellekten, istek atmaz) |
| GET | `/api/squad` | Kadro ve sezon istatistikleri |
| GET | `/api/absences` | Sakatlık ve ceza raporu (`source`: `api` / `manual`) |
| GET | `/api/standings/{super_lig\|uefa}` | Puan durumu |
| GET | `/api/live` | Canlı maç durumu (WebSocket açamayan istemciler için) |
| WS | `/ws/live` | Canlı skor, olaylar, gol bildirimi |
| GET | `/api/forum/posts?room=genel` | Oda mesajları |
| POST | `/api/forum/posts` | Mesaj gönder (IP başına 4 sn sınır) |
| POST | `/api/forum/posts/{id}/react` | Tepki (🔥 / ❤️) |
| POST | `/api/forum/posts/{id}/delete` | Kendi mesajını sil |
| GET | `/api/forum/next-match` | Açık maç odası |
| WS | `/ws/forum` | Yeni mesaj, tepki ve çevrimiçi sayısı |

## Klasör yapısı

```
FenerHub/
├── backend/
│   ├── app/
│   │   ├── main.py            uygulama, CORS, açılışta migration ve arka plan işleri
│   │   ├── database.py        bağlantı (Postgres ya da SQLite)
│   │   ├── models.py          SQLAlchemy modelleri
│   │   ├── sync.py            SportsAPI -> veritabanı
│   │   ├── auto_sync.py       bütçeli periyodik senkron
│   │   ├── live.py            canlı maç WebSocket istemcisi ve /ws/live
│   │   ├── absences_sync.py   eksik oyuncu listesinden otomatik sakatlık raporu
│   │   ├── cache.py           API önbelleği (api_cache tablosu)
│   │   ├── forum.py           12. Adam sohbeti
│   │   ├── net.py             proxy arkasında gerçek istemci IP'si
│   │   ├── migrate.py         açılışta Alembic migration'ları
│   │   └── routers/           matches, squad, standings, absences
│   ├── migrations/            Alembic sürümleri
│   ├── scripts/               elle çalıştırılan araçlar
│   ├── tests/                 pytest
│   └── requirements.txt       sabit sürümler
├── frontend/
│   ├── index.html
│   ├── css/style.css
│   ├── js/                    api, matchEngine (simülasyon), commentary (anlatıcı), forum, fx, nav
│   ├── tests/                 node --test
│   ├── img/                   logolar ve favicon
│   └── frames/                kaydırmaya bağlı arka plan animasyonu kareleri
├── tools/extract.py           videolardan arka plan karesi çıkarma (geliştirme aracı)
├── docs/                      teknik kararlar, yol haritası, geliştirme rehberi, ekran görüntüleri
└── .github/workflows/ci.yml   GitHub Actions
```
