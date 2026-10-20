# FenerHub

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Neon-4169E1?logo=postgresql&logoColor=white)
![JavaScript](https://img.shields.io/badge/JavaScript-vanilla-F7DF1E?logo=javascript&logoColor=black)
[![Lisans: MIT](https://img.shields.io/badge/Lisans-MIT-green.svg)](LICENSE)

Fenerbahçe taraftarları için canlı maç merkezi: canlı skor ve 2D maç simülasyonu, kadro istatistikleri,
puan durumu, sezon fikstürü ve taraftar sohbeti.

**[Canlı demo](https://fenerhub.vercel.app)** · **[API dokümanı](https://fenerhub.onrender.com/docs)** · **[Teknik kararlar](docs/teknik-kararlar.md)**

![Ana sayfa](docs/screenshots/anasayfa.png)

| Simülasyon ve canlı anlatım | Sezon fikstürü | Mobil |
|---|---|---|
| ![Simülasyon](docs/screenshots/simulasyon.png) | ![Fikstür](docs/screenshots/fikstur.png) | ![Mobil](docs/screenshots/mobil.png) |

## Öne çıkanlar

- **Canlı veri, ücretsiz kotayla:** Günde 100 isteklik plana bütçe kuralı, veritabanında önbellek ve uyarlanan sorgu aralıklarıyla sığıyor.
- **WebSocket proxy:** Maç saatinde backend tek bağlantıyla canlı veriyi alır ve tüm izleyicilere yayar. API anahtarı tarayıcıya gitmez.
- **Gerçek olaylarla simülasyon:** Goller, kartlar, değişiklikler ve VAR sahada canlanır; şablonlu bir spiker her olayı anlatır.
- **Veri kaybı olmadan altyapı:** SQLite'tan PostgreSQL'e geçiş, komut satırı olmayan sunucuda açılışta çalışan migration'lar.
- **Testli:** 33 backend (pytest) ve 7 frontend (`node --test`) testi, GitHub Actions iş akışı.

## Teknolojiler

**Backend:** Python, FastAPI, SQLAlchemy, Alembic, WebSocket · **Veritabanı:** PostgreSQL (Neon) ·
**Frontend:** Vanilla JavaScript, CSS, Canvas · **Altyapı:** Render, Vercel, GitHub Actions · **Veri:** SportsAPI Pro

```mermaid
flowchart LR
    SA[SportsAPI Pro<br/>REST + WebSocket] --> BE[FastAPI · Render<br/>senkron + canlı maç]
    BE <--> DB[(PostgreSQL · Neon)]
    BE -->|REST + WebSocket| FE[Vanilla JS · Vercel]
```

## Çalıştırma

```bash
cd backend
pip install -r requirements-dev.txt
cp .env.example .env               # SPORTS_API_KEY'i yazın
uvicorn app.main:app --reload      # frontend: frontend/ klasörünü statik sunun
```

Ayrıntılar (testler, araçlar, ortam değişkenleri, API, klasör yapısı): **[docs/gelistirme.md](docs/gelistirme.md)** ·
Yol haritası: **[docs/ROADMAP.md](docs/ROADMAP.md)**

---

**English:** FenerHub is a fan-made live match center for Fenerbahçe built with FastAPI, PostgreSQL and vanilla
JavaScript. It fits a 100-requests/day API plan through budgeting and caching, relays live match events to all
viewers over its own WebSocket channel, and animates real goals, cards and substitutions in a 2D simulation.

Taraftar projesidir; Fenerbahçe SK ile resmi bir bağlantısı yoktur. · [MIT Lisansı](LICENSE)
