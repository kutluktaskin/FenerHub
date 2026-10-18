"""SportsAPI -> veritabanı (sadece Fenerbahçe).

  python sync.py --offline   # kayıtlı sayfaları kullanır, istek harcamaz
  python sync.py             # eksik sayfaları API'den çeker

Oyuncu istatistikleri (maç/gol/asist) 6 saatte bir API'den yenilenir.
Arada çalışırsa player_stats_cache.json dosyasındaki kayıtlı değerler kullanılır,
yani istek harcanmaz.
"""
import os
import sys
import json
import time
from datetime import datetime, timezone, timedelta

import requests
from dotenv import load_dotenv

from app.database import Base, SessionLocal, engine
from app import models

load_dotenv()
BASE = "https://api.sportsapipro.com/v2/football/api"
FB_ID = 3052
SEASON_START = 1782864000  # 1 Temmuz 2026 (UTC); öncesi eski sezon
TR_TZ = timezone(timedelta(hours=3))
OFFLINE = "--offline" in sys.argv

# API adı -> veritabanındaki (seed) ad
ALIASES = {
    "SK Slavia Praha": "Slavia Prag",
    "Liverpool FC": "Liverpool",
    "LASK": "LASK Linz",
    "SK Sturm Graz": "Sturm Graz",
}

# Kadroda olmayan oyuncular: API listesinde olsa bile eklenmez, varsa veritabanından silinir.
EXCLUDE_PLAYERS = {"Jayden Oosterwolde"}

# Oyuncu istatistiği ayarları
STATS_SEASON = "2026-27"
STATS_START_YEAR = 2026
STATS_TOURNAMENTS = {"Trendyol Süper Lig", "UEFA Champions League"}
STATS_CACHE = "player_stats_cache.json"
STATS_MAX_AGE = 6 * 3600  # saniye
# Puan durumu ayarları
STANDINGS = {
    "super_lig": (52, 98080),
    "uefa": (7, 96518),
}
STANDINGS_CACHE = "standings_cache.json"
STANDINGS_MAX_AGE = 3600  # saniye

def api_get(path):
    headers = {"x-api-key": os.environ["SPORTS_API_KEY"], "User-Agent": "curl/8"}
    for attempt in range(4):
        r = requests.get(BASE + path, headers=headers, timeout=30)
        print(f"deneme {attempt + 1}: {path} -> {r.status_code}")
        if r.status_code in (503, 504) and attempt < 3:
            time.sleep(5 * (attempt + 1))
            continue
        break
    r.raise_for_status()
    return r.json()


def fetch_events():
    """Takım ucundan sayfaları çeker, pages_fb/ klasörüne kaydeder. Kayıtlı sayfayı tekrar istemez."""
    os.makedirs("pages_fb", exist_ok=True)
    by_id = {}
    complete = True
    for direction, max_pages in (("next", 2), ("last", 1)):
        for page in range(max_pages):
            fn = f"pages_fb/{direction}_{page}.json"
            if os.path.exists(fn):
                with open(fn, encoding="utf-8") as f:
                    evs = json.load(f)
            elif OFFLINE:
                break
            else:
                try:
                    data = api_get(f"/teams/{FB_ID}/events/{direction}/{page}")
                except requests.exceptions.HTTPError as err:
                    print(f"!! {direction}/{page} alınamadı ({err}). Sonra tekrar çalıştır.")
                    complete = False
                    break
                evs = (data.get("data") or {}).get("events") or []
                with open(fn, "w", encoding="utf-8") as f:
                    json.dump(evs, f, ensure_ascii=False)
            if not evs:
                break
            for e in evs:
                by_id[e["id"]] = e
    print("Toplam benzersiz maç:", len(by_id), "| tamam mı:", complete)
    return list(by_id.values())


def fetch_squad():
    if OFFLINE:
        with open("squad_raw.json", encoding="utf-8") as f:
            return json.load(f)["data"]["players"]
    data = api_get(f"/teams/{FB_ID}/players")
    with open("squad_raw.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return data["data"]["players"]


def summarize_stats(payload):
    """API cevabından bu sezonun Fenerbahçe maç/gol/asist toplamını çıkarır
    (Süper Lig + Şampiyonlar Ligi). Milli takım ve hazırlık maçları sayılmaz."""
    total = {"appearances": 0, "goals": 0, "assists": 0}
    seasons = (payload.get("data") or {}).get("seasons") or []
    for s in seasons:
        team = s.get("team") or {}
        tournament = (s.get("uniqueTournament") or {}).get("name")
        if (
            s.get("startYear") != STATS_START_YEAR
            or team.get("id") != FB_ID
            or tournament not in STATS_TOURNAMENTS
        ):
            continue
        st = s.get("statistics") or {}
        for key in total:
            total[key] += st.get(key) or 0
    return total


def fetch_player_stats(items):
    """{oyuncu adı: {appearances, goals, assists}} döndürür.
    Önbellek 6 saatten tazeyse (ya da --offline ise) API'ye istek atmaz."""
    cache = {}
    if os.path.exists(STATS_CACHE):
        with open(STATS_CACHE, encoding="utf-8") as f:
            cache = json.load(f)
    old = cache.get("stats", {})
    fresh = time.time() - cache.get("fetched_at", 0) < STATS_MAX_AGE

    if fresh or OFFLINE:
        if not old:
            print("Oyuncu istatistiği önbelleği yok, atlandı (--offline).")
        else:
            print("Oyuncu istatistikleri önbellekten kullanıldı (istek harcanmadı).")
        return old

    stats = {}
    all_ok = True
    for item in items:
        p = item["player"]
        if p["name"] in EXCLUDE_PLAYERS or not p.get("id"):
            continue
        try:
            payload = api_get(f"/players/{p['id']}/statistics")
            stats[p["name"]] = summarize_stats(payload)
        except (requests.exceptions.RequestException, KeyError, ValueError) as err:
            print(f"!! {p['name']} istatistiği alınamadı ({err}). Eski değer korunuyor.")
            all_ok = False
            if p["name"] in old:
                stats[p["name"]] = old[p["name"]]
        time.sleep(0.3)

    with open(STATS_CACHE, "w", encoding="utf-8") as f:
        # Hata olduysa fetched_at=0 yaz: bir sonraki çalıştırmada tekrar denenir
        json.dump({"fetched_at": time.time() if all_ok else 0, "stats": stats}, f, ensure_ascii=False)
    print(f"Oyuncu istatistikleri API'den çekildi: {len(stats)} oyuncu")
    return stats

def fetch_standings():
    """{'super_lig': [...], 'uefa': [...]} döndürür. Önbellek 1 saatten tazeyse
    (ya da --offline ise) API'ye istek atmaz."""
    cache = {}
    if os.path.exists(STANDINGS_CACHE):
        with open(STANDINGS_CACHE, encoding="utf-8") as f:
            cache = json.load(f)
    old = cache.get("tables", {})
    fresh = time.time() - cache.get("fetched_at", 0) < STANDINGS_MAX_AGE

    if fresh or OFFLINE:
        print("Puan durumu önbellekten kullanıldı (istek harcanmadı).")
        return old

    tables = {}
    all_ok = True
    for key, (tid, sid) in STANDINGS.items():
        try:
            data = api_get(f"/tournament/{tid}/season/{sid}/standings")
            rows = []
            for r in data.get("standings") or []:
                rows.append({
                    "position": r["position"],
                    "team": ALIASES.get(r["teamName"], r["teamName"]),
                    "played": r["played"],
                    "won": r["won"],
                    "drawn": r["drawn"],
                    "lost": r["lost"],
                    "goals_for": r["goalsFor"],
                    "goals_against": r["goalsAgainst"],
                    "goal_diff": r["goalsFor"] - r["goalsAgainst"],
                    "points": r["points"],
                })
            tables[key] = rows
        except (requests.exceptions.RequestException, KeyError, ValueError) as err:
            print(f"!! {key} puan durumu alınamadı ({err}). Eski değer korunuyor.")
            all_ok = False
            if key in old:
                tables[key] = old[key]

    with open(STANDINGS_CACHE, "w", encoding="utf-8") as f:
        json.dump({"fetched_at": time.time() if all_ok else 0, "tables": tables},
                  f, ensure_ascii=False)
    print("Puan durumu API'den çekildi:", {k: len(v) for k, v in tables.items()})
    return tables

def upsert_team(db, t):
    name = ALIASES.get(t["name"], t["name"])
    team = db.query(models.Team).filter_by(name=name).first()
    if not team:
        team = models.Team(name=name, short_name=t.get("shortName") or t.get("nameCode"))
        db.add(team)
        db.flush()
    return team


def map_status(status):
    return {"inprogress": "live", "finished": "finished"}.get((status or {}).get("type"), "scheduled")


def score(d):
    v = (d or {}).get("current")
    return v if isinstance(v, int) else None


def competition_of(e):
    name = (e.get("tournament") or {}).get("name", "")
    if "Süper Lig" in name:
        return "super_lig", True
    if "Champions League" in name:
        return "uefa", name.strip() == "UEFA Champions League"  # ikinci değer: hafta numarası güvenilir mi
    return None, False


def sync_matches(db, events):
    created = updated = skipped = 0
    for e in events:
        comp, round_ok = competition_of(e)
        if not comp or e["startTimestamp"] < SEASON_START:
            skipped += 1
            continue
        home = upsert_team(db, e["homeTeam"])
        away = upsert_team(db, e["awayTeam"])
        dt = datetime.fromtimestamp(e["startTimestamp"], TR_TZ)
        rnd = (e.get("roundInfo") or {}).get("round")
        st = e.get("status") or {}
        t = e.get("time") or {}
        live = st.get("type") == "inprogress"
        fields = dict(
            matchday=rnd if (round_ok and isinstance(rnd, int) and rnd < 100) else None,
            match_date=dt.date(),
            kickoff_time=dt.time(),
            home_score=score(e.get("homeScore")),
            away_score=score(e.get("awayScore")),
            status=map_status(st),
            minute=None,
            status_code=st.get("code") if live else None,
            period_start=t.get("currentPeriodStartTimestamp") if live else None,
            period_initial=t.get("initial") if live else None,
        )
        m = (
            db.query(models.Match)
            .filter_by(competition=comp, home_team_id=home.id, away_team_id=away.id)
            .first()
        )
        if m:
            for k, v in fields.items():
                setattr(m, k, v)
            updated += 1
        else:
            db.add(models.Match(competition=comp, home_team_id=home.id, away_team_id=away.id, **fields))
            created += 1
    print(f"Maçlar: {created} yeni, {updated} güncellendi, {skipped} atlandı (eski sezon/hazırlık/kupa)")


def sync_squad(db, items):
    team = upsert_team(db, items[0]["player"]["team"])
    seen = set()
    created = updated = 0
    for item in items:
        p = item["player"]
        if p["name"] in EXCLUDE_PLAYERS:
            continue
        shirt = p.get("shirtNumber")
        if shirt is None:
            try:
                shirt = int(p.get("jerseyNumber"))
            except (TypeError, ValueError):
                shirt = None
        row = db.query(models.Player).filter_by(name=p["name"], team_id=team.id).first()
        if row:
            row.position = p.get("position")
            row.shirt_number = shirt
            updated += 1
        else:
            db.add(models.Player(name=p["name"], position=p.get("position"), shirt_number=shirt, team_id=team.id))
            created += 1
        seen.add(p["name"])
    print(f"Kadro ({team.name}): {created} yeni, {updated} güncellendi")
    stale = [pl.name for pl in db.query(models.Player).filter_by(team_id=team.id).all() if pl.name not in seen]
    if stale:
        print("API kadrosunda olmayan ama veritabanında duran oyuncular:", stale)
    return team


def remove_excluded(db):
    """Hariç tutulan oyuncuları ve onlara bağlı sakatlık/istatistik kayıtlarını siler."""
    for name in EXCLUDE_PLAYERS:
        for pl in db.query(models.Player).filter_by(name=name).all():
            db.query(models.Absence).filter_by(player_id=pl.id).delete()
            db.query(models.PlayerStat).filter_by(player_id=pl.id).delete()
            db.delete(pl)
            print(f"Kadrodan çıkarıldı: {name}")


def sync_player_stats(db, team, stats):
    updated = 0
    for name, s in stats.items():
        if name in EXCLUDE_PLAYERS:
            continue
        player = db.query(models.Player).filter_by(name=name, team_id=team.id).first()
        if not player:
            continue
        row = (
            db.query(models.PlayerStat)
            .filter_by(player_id=player.id, season=STATS_SEASON)
            .first()
        )
        if row:
            row.appearances = s["appearances"]
            row.goals = s["goals"]
            row.assists = s["assists"]
        else:
            db.add(models.PlayerStat(
                player_id=player.id, season=STATS_SEASON,
                appearances=s["appearances"], goals=s["goals"], assists=s["assists"],
            ))
        updated += 1
    print(f"Oyuncu istatistikleri: {updated} oyuncu güncellendi")


def main():
    Base.metadata.create_all(bind=engine)
    events = fetch_events()
    squad = fetch_squad()
    stats = fetch_player_stats(squad)
    fetch_standings()
    db = SessionLocal()
    try:
        sync_matches(db, events)
        team = sync_squad(db, squad)
        db.flush()
        remove_excluded(db)
        sync_player_stats(db, team, stats)
        db.commit()
        print("Tamam.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    main()