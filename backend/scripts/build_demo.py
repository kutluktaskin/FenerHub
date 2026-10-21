"""Canlı maç kaydından demo dosyası üretir (sitede ?demo=live ile oynatılır).

  python -m scripts.build_demo                                   # 20 Ekim Slavia kaydı
  python -m scripts.build_demo --record scripts/probe_ws_record_<id>.jsonl --api-id <id> --out ../frontend/demo/<ad>.json

Girdi: scripts/probe_ws_record.py'nin SportsAPI WebSocket kaydı (repoya girmez, ~30 MB).
Çıktı: sitenin kendi /ws/live mesaj biçiminde küçük bir zaman çizelgesi:
  {"meta": {...}, "events": [[saniye, mesaj], ...]}
  - ilk mesaj "state" (maç bilgisi, kadro), sonra "update" (match / incidents / statistics / lineups)
  - aynı içerik tekrar edilmez; istatistikler en fazla 2 dakikada bir alınır (dosya küçük kalsın)
Maç durumu canlı sistemdeki fonksiyonlarla kurulur (app.live.event_fields / apply_event),
yani demo gerçek canlı akışla aynı mantıktan geçer.
"""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from app import live
from app.database import SessionLocal
from app.routers.matches import match_query, serialize_match, trim_incidents, trim_lineups, trim_stats
from app import models

BACKEND = Path(__file__).resolve().parents[1]
STATS_EVERY = 120          # sn: istatistik güncellemelerini seyrelt
LEAD_IN = 120              # sn: başlama düdüğünden önce oynatmaya başla
TAIL = 90                  # sn: maç sonundan sonra devam et
MATCH_FIELDS = ("status", "status_code", "period_start", "period_initial", "home_score", "away_score")


def load(path: Path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            yield row["t"], row["msg"]


def build(record: Path, api_id: int, base_match: dict) -> dict:
    rows = [(t, m) for t, m in load(record) if "data" in m and m.get("channel", "").startswith(f"match:{api_id}")]
    rows.sort(key=lambda r: r[0])
    kind_of = lambda ch: (ch.split(":") + [""])[2]

    # Başlama ve bitiş anı: match kanalındaki ilk "1. yarı" ve "bitti" mesajları
    kickoff = next(t for t, m in rows if kind_of(m["channel"]) == "" and m["data"].get("status.code") == 6)
    ended = next((t for t, m in rows if kind_of(m["channel"]) == "" and m["data"].get("status.code") == 100), rows[-1][0])
    start, end = kickoff - LEAD_IN, ended + TAIL

    match = SimpleNamespace(**{k: base_match.get(k) for k in MATCH_FIELDS})
    match.status, match.status_code, match.period_start, match.period_initial = "scheduled", None, None, None
    match.home_score = match.away_score = None

    def match_dict():
        return {**base_match, **{k: getattr(match, k) for k in MATCH_FIELDS}}

    # Başlangıç durumu: oynatma başına kadar gelen son kadro
    lineups = None
    for t, m in rows:
        if t > start:
            break
        if kind_of(m["channel"]) == "lineups":
            lineups = trim_lineups(m["data"]) or lineups
    events = [[0, {"type": "state", "match_id": "demo", "source": "ws", "match": match_dict(),
                   "incidents": [], "statistics": None, "lineups": lineups}]]

    dump = lambda x: json.dumps(x, ensure_ascii=False)
    last = {"match": dump(match_dict()), "incidents": "[]", "statistics": "null", "lineups": dump(lineups)}
    incidents_raw, stats_at = None, -1e9
    for t, m in rows:
        if t < start or t > end:
            continue
        kind = {"": "match", "incidents": "incidents", "stats": "statistics", "lineups": "lineups"}.get(kind_of(m["channel"]))
        data = m["data"]
        if kind == "match":
            f = live.event_fields(data)
            if not f:
                continue
            live.apply_event(match, f)
            out = match_dict()
        elif kind == "incidents":
            incidents_raw = live.merge_incidents(incidents_raw, data)
            out = trim_incidents(incidents_raw)
        elif kind == "statistics":
            if data.get("error") or (t - stats_at < STATS_EVERY and t < ended):
                continue
            out = trim_stats(data)
        elif kind == "lineups":
            out = trim_lineups(data)
        else:
            continue
        if out is None:
            continue
        text = dump(out)
        if text == last[kind]:
            continue
        last[kind] = text
        if kind == "statistics":
            stats_at = t
        events.append([round(t - start, 1), {"type": "update", "kind": kind, "data": out}])

    final = match_dict()
    return {
        "meta": {
            "title": f"{final['home']} {final['home_score']}-{final['away_score']} {final['away']}",
            "date": base_match.get("match_date"),
            "competition": base_match.get("competition"),
            "duration": round(end - start),
            "kickoff_offset": LEAD_IN,
            "start": start,             # kaydın 0. saniyesinin Unix zamanı (dakika sayacı için)
        },
        "events": events,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", default=str(BACKEND / "scripts" / "probe_ws_record_16938965.jsonl"))
    ap.add_argument("--api-id", type=int, default=16938965)
    ap.add_argument("--out", default=str(BACKEND.parent / "frontend" / "demo" / "slavia-2026-10-20.json"))
    args = ap.parse_args()

    with SessionLocal() as db:
        m = match_query(db).filter(models.Match.api_id == args.api_id).first()
        if not m:
            raise SystemExit(f"Maç veritabanında yok: {args.api_id}")
        base = serialize_match(m)
    base["id"] = "demo"

    demo = build(Path(args.record), args.api_id, base)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(demo, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    kinds = {}
    for _, e in demo["events"][1:]:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    print(f"{demo['meta']['title']} · {demo['meta']['duration'] // 60} dk · {len(demo['events'])} mesaj {kinds} "
          f"· {out.stat().st_size // 1024} KB -> {out}")


if __name__ == "__main__":
    main()
