"""Canlı maç: SportsAPI WebSocket -> sitenin kendi /ws/live kanalı.

- Fenerbahçe maçı başlamadan 15 dk önce backend SportsAPI WebSocket'ine bağlanır
  (kotadan düşmez), maç bitince (FT + 10 dk) ya da en geç başlangıçtan 4 saat sonra kapatır.
- API anahtarı sadece bu bağlantının başlığında gider; tarayıcıya hiçbir zaman gitmez.
- Kopunca 2, 4, 8 ... en fazla 60 sn bekleyerek yeniden bağlanır. 2 dakikadan uzun süre
  bağlanamazsa REST yedeği devreye girer: 60 sn'de bir olaylar (kota azsa 5 dk'da bir,
  günlük bütçe dolmuşsa hiç).
- Gelen veri api_cache'e (detail:<id>:<tür>) REST ile aynı biçimde yazılır, böylece
  /api/matches/{id}/detail ve auto_sync aynı veriyi görür. Skor/durum matches tablosuna işlenir.
- Tarayıcılar /ws/live'a bağlanır: önce o anki durumun tamamı ("state"), sonra her
  değişiklik ("update") ve gol anında ayrıca "goal" mesajı gelir.
"""
import asyncio
import json
import os
import time
import traceback
from datetime import datetime, timedelta

import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from . import absences_sync, cache, models, sync
from .database import SessionLocal
from .routers.matches import match_query, serialize_match, trim_incidents, trim_lineups, trim_stats

URL = "wss://api.sportsapipro.com/v2/football/ws"

PRE_MATCH = timedelta(minutes=15)      # başlamadan bu kadar önce bağlan
MAX_LENGTH = timedelta(hours=4)        # FT hiç gelmezse en geç burada kapat
AFTER_FT = 10 * 60                     # FT'den sonra son istatistikler için açık kalma süresi (sn)
CHECK_EVERY = 30                       # maç var mı kontrol aralığı (sn)
RECV_TIMEOUT = 30                      # mesaj gelmese de bu aralıkla bitiş koşuluna bakılır

FALLBACK_AFTER = 120                   # WS bu kadar süredir yoksa REST yedeği başlar (sn)
FALLBACK_EVERY = 60
FALLBACK_SLOW = 300
QUOTA_SLOW = 55                        # kalan günlük kota bunun altındaysa yedek yavaşlar
QUOTA_STOP = 40                        # 100'ün %60'ı kullanıldı: yedek durur

# WS kanal soneki -> önbellekteki tür adı (REST uçlarıyla aynı)
KINDS = {"incidents": "incidents", "stats": "statistics", "lineups": "lineups"}
TRIM = {"incidents": trim_incidents, "statistics": trim_stats, "lineups": trim_lineups}

router = APIRouter(tags=["live"])

covered: set[int] = set()              # şu an WebSocket'le izlenen maçların api id'leri
state: dict = {}                       # tarayıcılara giden güncel durum (tek maç)


def covers(api_id) -> bool:
    """auto_sync bu maç için REST isteği atmasın mı? İzlenen maçın verisi WS'ten ya da
    (WS uzun süre yoksa) buradaki bütçeli REST yedeğinden gelir; iki taraf aynı isteği atmasın."""
    return api_id in covered


# ---------- Tarayıcı tarafı: /ws/live ----------
class LiveHub:
    def __init__(self):
        self.clients: set[WebSocket] = set()

    async def broadcast(self, data):
        for ws in list(self.clients):
            try:
                await ws.send_json(data)
            except Exception:
                self.clients.discard(ws)


hub = LiveHub()


@router.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    await websocket.accept()
    hub.clients.add(websocket)
    try:
        await websocket.send_json({"type": "state", **state} if state else {"type": "idle"})
        while True:
            await websocket.receive_text()          # istemci bir şey göndermez; bağlantıyı tutar
    except WebSocketDisconnect:
        pass
    finally:
        hub.clients.discard(websocket)


@router.get("/api/live")
def live_state():
    """WebSocket açamayan istemciler için aynı durum (REST)."""
    return {"type": "state", **state} if state else {"type": "idle"}


# ---------- Hangi maç izlenecek ----------
def pick_match(now: datetime | None = None):
    """Şu an izlenmesi gereken Fenerbahçe maçı: başlamasına 15 dk'dan az kalmış ya da
    başlamış, bitmemiş ve 4 saatten eski olmayan ilk maç."""
    now = now or datetime.now(sync.TR_TZ)
    with SessionLocal() as db:
        rows = db.query(models.Match).filter(
            models.Match.status != "finished",
            models.Match.api_id.is_not(None),
            models.Match.match_date.is_not(None),
            models.Match.kickoff_time.is_not(None),
        ).all()
        for m in sorted(rows, key=lambda r: (r.match_date, r.kickoff_time)):
            ko = datetime.combine(m.match_date, m.kickoff_time, tzinfo=sync.TR_TZ)
            if ko - PRE_MATCH <= now <= ko + MAX_LENGTH and not cache.get(f"detail:{m.api_id}:done"):
                return {"id": m.id, "api_id": m.api_id, "kickoff": ko.timestamp()}
    return None


# ---------- Gelen veriyi işleme ----------
def is_finished(incidents) -> bool:
    return any(i.get("incidentType") == "period" and i.get("text") == "FT" for i in incidents or [])


def score_from(incidents):
    """Olay listesindeki en son skor (gol ve devre olayları skoru taşır)."""
    best = None
    for i in incidents or []:
        if i.get("homeScore") is None or i.get("awayScore") is None:
            continue
        k = (i.get("time") or 0, i.get("addedTime") if i.get("addedTime") not in (None, 999) else 0)
        if best is None or k >= best[0]:
            best = (k, (i["homeScore"], i["awayScore"]))
    return best[1] if best else None


def merge_incidents(old, data):
    """Kanal ya da REST tam listeyi gönderir; tek olay gelirse id'sine göre listeye eklenir."""
    if isinstance(data, dict) and isinstance(data.get("incidents"), list):
        return data
    if isinstance(data, dict) and data.get("incidentType"):
        base = dict(old or {"incidents": []})
        items = [i for i in base.get("incidents") or [] if not (data.get("id") and i.get("id") == data["id"])]
        base["incidents"] = [data, *items]
        return base
    return old


def save_match(match_id, home, away, status=None):
    """Canlı skoru/durumu matches tablosuna yazar; değişen maçın güncel hâlini döndürür."""
    with SessionLocal() as db, db.begin():
        m = match_query(db).filter(models.Match.id == match_id).first()
        if not m:
            return None
        if home is not None:
            m.home_score, m.away_score = home, away
        if status:
            m.status = status
        db.flush()
        return serialize_match(m)


def load_match(match_id):
    with SessionLocal() as db:
        m = match_query(db).filter(models.Match.id == match_id).first()
        return serialize_match(m) if m else None


def unflatten(data: dict) -> dict:
    """WS match kanalı alanları noktalı düz anahtarlarla gönderir ("status.code": 31);
    iç içe biçime çevirir ({"status": {"code": 31}}). İç içe gelen alanlar olduğu gibi kalır."""
    out: dict = {}
    for key, value in data.items():
        node = out
        *path, last = key.split(".")
        for part in path:
            node = node.setdefault(part, {}) if isinstance(node.get(part, {}), dict) else node
        node[last] = value
    return out


# Canlı sayılan durum kodları: 6 ilk yarı, 7 ikinci yarı, 31 devre arası, uzatmalar ve penaltılar
LIVE_CODES = {6, 7, 31, 32, 33, 34, 41, 42, 50}


def event_fields(data):
    """match:{id} kanalının skor/durum mesajından alanlar. Mesajlar kısmidir: sadece değişen
    alanlar gelir (ör. devre arasında yalnız status.code=31). Gelmeyen alan None'dır ve
    veritabanındaki değeri değiştirmez. Kayıt: 20 Ekim Slavia maçı (scripts/probe_ws_record.py)."""
    if not isinstance(data, dict):
        return None
    ev = data.get("event") if isinstance(data.get("event"), dict) else unflatten(data)
    st = ev.get("status") if isinstance(ev.get("status"), dict) else {}
    tm = ev.get("time") if isinstance(ev.get("time"), dict) else {}
    f = {
        "home": sync.score(ev.get("homeScore")),
        "away": sync.score(ev.get("awayScore")),
        "status_type": st.get("type"),
        "status_code": st.get("code"),
        "period_start": tm.get("currentPeriodStartTimestamp"),
        "period_initial": tm.get("initial"),
    }
    return f if any(v is not None for v in f.values()) else None


def save_event(match_id, f):
    """Kısmi durum mesajını maça işler; değişen maçın güncel hâlini döndürür."""
    with SessionLocal() as db, db.begin():
        m = match_query(db).filter(models.Match.id == match_id).first()
        if not m:
            return None
        code = f.get("status_code")
        if f.get("status_type"):
            m.status = sync.map_status({"type": f["status_type"]})
        elif code == 100:
            m.status = "finished"
        elif code in LIVE_CODES:
            m.status = "live"
        if m.status == "live":
            if code is not None:
                m.status_code = code
            if f.get("period_start") is not None:
                m.period_start = f["period_start"]
            if f.get("period_initial") is not None:
                m.period_initial = f["period_initial"]
        elif m.status == "finished":
            m.status_code = m.period_start = m.period_initial = None
        # Skor mesajları da kısmi: golde sadece atan tarafın skoru gelir. Maç başlamadan gelen
        # 0-0 mesajı kartı "0 - 0" göstermesin diye sadece başlamış maçta işlenir.
        if m.status != "scheduled" and (f.get("home") is not None or f.get("away") is not None):
            if f.get("home") is not None:
                m.home_score = f["home"]
            if f.get("away") is not None:
                m.away_score = f["away"]
            m.home_score = m.home_score or 0
            m.away_score = m.away_score or 0
        db.flush()
        return serialize_match(m)


class Follower:
    """Tek bir maçı baştan sona izler."""

    def __init__(self, target):
        self.match_id = target["id"]
        self.api_id = target["api_id"]
        self.kickoff = target["kickoff"]
        self.ft_at = None
        self.last_rest = 0.0
        self.score = None

    def done(self) -> bool:
        now = time.time()
        return (self.ft_at is not None and now > self.ft_at + AFTER_FT) or \
            now > self.kickoff + MAX_LENGTH.total_seconds()

    async def start(self):
        state.clear()
        state.update({
            "match_id": self.match_id, "api_id": self.api_id, "source": "connecting",
            "match": await run_in_threadpool(load_match, self.match_id),
            "incidents": None, "statistics": None, "lineups": None, "updated": time.time(),
        })
        for kind in ("incidents", "statistics", "lineups"):    # önbellekte ne varsa hemen göster
            data = await run_in_threadpool(cache.get, f"detail:{self.api_id}:{kind}")
            if data:
                state[kind] = TRIM[kind](data.get("data"))
        self.score = score_from((await run_in_threadpool(cache.get, f"detail:{self.api_id}:incidents")
                                 or {}).get("data", {}).get("incidents"))
        await hub.broadcast({"type": "state", **state})

    async def set_source(self, source):
        if state.get("source") != source:
            state["source"] = source
            print(f"Canlı maç {self.api_id}: kaynak = {source}", flush=True)
            await hub.broadcast({"type": "source", "source": source})

    async def handle_kind(self, kind, data):
        """Olay/istatistik/kadro verisi geldi (WS ya da REST). data = API'nin 'data' alanı."""
        if not isinstance(data, dict) or data.get("error"):
            return
        key = f"detail:{self.api_id}:{kind}"
        if kind == "incidents":
            old = await run_in_threadpool(cache.get, key)
            data = merge_incidents((old or {}).get("data"), data)
            if data is None:
                return
        await run_in_threadpool(cache.put, key, {"data": data})
        state[kind] = TRIM[kind](data)
        state["updated"] = time.time()
        await hub.broadcast({"type": "update", "kind": kind, "data": state[kind]})
        if kind == "lineups":
            await run_in_threadpool(absences_sync.apply_lineups, self.api_id, data)

        if kind != "incidents":
            return
        incidents = data.get("incidents")
        new_score = score_from(incidents)
        finished = is_finished(incidents)
        if new_score and new_score != self.score:
            old_score, self.score = self.score, new_score
            match = await run_in_threadpool(save_match, self.match_id, *new_score,
                                            "finished" if finished else "live")
            if match:
                state["match"] = match
                await hub.broadcast({"type": "update", "kind": "match", "data": match})
            if old_score and sum(new_score) > sum(old_score):
                goal = next((i for i in state["incidents"] or [] if i["incidentType"] == "goal"), None)
                await hub.broadcast({"type": "goal", "score": new_score, "incident": goal})
        if finished and self.ft_at is None:
            self.ft_at = time.time()
            await run_in_threadpool(cache.put, f"detail:{self.api_id}:done", True)
            match = await run_in_threadpool(save_match, self.match_id, None, None, "finished")
            if match:
                state["match"] = match
                await hub.broadcast({"type": "update", "kind": "match", "data": match})
            print(f"Canlı maç {self.api_id}: bitti (FT), {AFTER_FT // 60} dk sonra kapanacak", flush=True)

    async def handle_event(self, data):
        f = event_fields(data)
        if not f:
            return
        match = await run_in_threadpool(save_event, self.match_id, f)
        if match:
            state["match"] = match
            state["updated"] = time.time()
            await hub.broadcast({"type": "update", "kind": "match", "data": match})

    async def handle(self, msg):
        parts = (msg.get("channel") or "").split(":")
        if "data" not in msg or parts[:2] != ["match", str(self.api_id)]:
            return              # welcome / subscribed / başka maç
        suffix = parts[2] if len(parts) > 2 else ""
        if suffix in KINDS:
            await self.handle_kind(KINDS[suffix], msg.get("data"))
        elif not suffix:
            await self.handle_event(msg.get("data"))

    def rest_interval(self):
        q = sync.quota_remaining
        if q is None or q > QUOTA_SLOW:
            return FALLBACK_EVERY
        if q > QUOTA_STOP:
            return FALLBACK_SLOW
        return None

    async def rest_fallback(self):
        every = self.rest_interval()
        if every is None or time.time() - self.last_rest < every:
            return
        self.last_rest = time.time()
        await self.set_source("rest")
        try:
            data = await run_in_threadpool(sync.api_get, f"/match/{self.api_id}/incidents")
            await self.handle_kind("incidents", data.get("data"))
        except Exception as e:
            print(f"Canlı maç REST yedeği hatası: {type(e).__name__}", flush=True)

    async def run(self):
        await self.start()
        covered.add(self.api_id)
        wait, down_since = 2, None
        print(f"Canlı maç {self.api_id}: izleme başladı", flush=True)
        try:
            while not self.done():
                try:
                    async with connect() as ws:
                        for suffix in ("", ":lineups", ":incidents", ":stats"):
                            await ws.send(json.dumps({"action": "subscribe",
                                                      "channel": f"match:{self.api_id}{suffix}"}))
                        await self.set_source("ws")
                        wait, down_since = 2, None
                        while not self.done():
                            try:
                                raw = await asyncio.wait_for(ws.recv(), timeout=RECV_TIMEOUT)
                            except asyncio.TimeoutError:
                                continue
                            try:
                                await self.handle(json.loads(raw))
                            except Exception:
                                traceback.print_exc()
                except Exception as e:
                    down_since = down_since or time.time()
                    print(f"Canlı maç WS bağlantısı yok ({type(e).__name__}); {wait} sn sonra "
                          "yeniden denenecek", flush=True)
                    if time.time() - down_since >= FALLBACK_AFTER:
                        await self.rest_fallback()
                    elif state.get("source") == "ws":
                        await self.set_source("reconnecting")
                    await asyncio.sleep(wait)
                    wait = min(wait * 2, 60)
        finally:
            covered.discard(self.api_id)
            print(f"Canlı maç {self.api_id}: izleme bitti", flush=True)
            state["source"] = "ended"
            await hub.broadcast({"type": "source", "source": "ended"})


def connect():
    headers = {"x-api-key": os.environ["SPORTS_API_KEY"], "x-sport": "football"}
    return websockets.connect(URL, additional_headers=headers, open_timeout=20,
                              ping_interval=20, max_size=None)


async def live_loop():
    """Uygulama boyunca çalışır: sırası gelen maçı bulup izler."""
    if not os.environ.get("SPORTS_API_KEY"):
        print("Canlı maç kapalı: SPORTS_API_KEY yok", flush=True)
        return
    while True:
        try:
            target = await run_in_threadpool(pick_match)
            if target:
                await Follower(target).run()
                continue
        except asyncio.CancelledError:
            raise
        except Exception:
            traceback.print_exc()
        await asyncio.sleep(CHECK_EVERY)
