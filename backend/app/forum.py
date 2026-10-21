"""12. Adam forumu: oda bazlı mesajlar, yanıt, tepki, silme ve /ws/forum canlı yayını."""
import hashlib
import hmac
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased
from starlette.concurrency import run_in_threadpool

from .database import SessionLocal
from .models import ForumPost, PostReport
from .net import client_ip
from .profanity import mask

forum_router = APIRouter(tags=["forum"])

# Mesajlar ana veritabanındaki posts tablosunda (eskiden ayrı forum.db; aktarım:
# scripts/migrate_to_postgres.py). Veritabanı işleri thread havuzunda çalışır ki
# Neon'un gecikmesi forumun WebSocket'ini bekletmesin.
ROOMS = {"genel", "transfer"}
TR = timezone(timedelta(hours=3))

# Maçları kronolojik sırayla ekle. Saatler Türkiye saatiyle (+03:00).
FIXTURES = [
    {"id": "slavia-1020", "home": "Fenerbahçe", "away": "Slavia Prag",
     "comp": "UEFA Şampiyonlar Ligi", "kickoff": "2026-10-20T19:45:00+03:00"},
    {"id": "gs-1026", "home": "Galatasaray", "away": "Fenerbahçe",
     "comp": "Trendyol Süper Lig", "kickoff": "2026-10-26T21:30:00+03:00"},
    {"id": "goztepe-1031", "home": "Fenerbahçe", "away": "Göztepe",
     "comp": "Trendyol Süper Lig", "kickoff": "2026-10-31T19:00:00+03:00"},
]

MATCH_LENGTH = timedelta(hours=2)   # maç süresi (yaklaşık)
KEEP_OPEN = timedelta(hours=24)     # maç bittikten sonra oda açık kalma süresi


def current_match():
    """Maç bitişinden (başlangıç + 2 saat) 24 saat geçmeyen ilk maç."""
    now = datetime.now(TR)
    for match in FIXTURES:
        kickoff = datetime.fromisoformat(match["kickoff"])
        if now < kickoff + MATCH_LENGTH + KEEP_OPEN:
            return match
    return None


def valid_room(room: str) -> bool:
    return room in ROOMS or room in {"mac-" + m["id"] for m in FIXTURES}


REPORT_LIMIT = 3                    # bu kadar farklı kullanıcı (IP) bildirince mesaj gizlenir
REPORTS_PER_HOUR = 20               # bir IP'nin saatte en fazla bildirim sayısı
last_post = {}                      # ip -> son mesaj zamanı
POST_INTERVAL = 4                   # aynı IP'den iki mesaj arası en az saniye
LAST_POST_TTL = 60                  # bundan eski kayıtlar sözlükten silinir
LAST_POST_MAX = 10_000              # üst sınır (temizlikten bağımsız güvence)
_last_prune = 0.0


def prune_last_post(now: float) -> None:
    """last_post sonsuza kadar büyümesin: en fazla dakikada bir eski kayıtları siler."""
    global _last_prune
    if now - _last_prune < LAST_POST_TTL and len(last_post) < LAST_POST_MAX:
        return
    _last_prune = now
    for key in [k for k, t in last_post.items() if now - t > LAST_POST_TTL]:
        del last_post[key]
    if len(last_post) >= LAST_POST_MAX:          # hepsi yeni olsa bile sınırı aşmasın
        for key in sorted(last_post, key=last_post.get)[: len(last_post) - LAST_POST_MAX + 1]:
            del last_post[key]


# Mesaj + yanıtlanan mesajın özeti (eski SELECT_POST sorgusunun karşılığı)
Parent = aliased(ForumPost)
SELECT_POST = (
    select(ForumPost, Parent.nick, Parent.body, Parent.deleted | Parent.hidden)
    .outerjoin(Parent, Parent.id == ForumPost.parent_id)
)


def row_to_post(row, owner: str = ""):
    """API cevabı: id, room, nick, body, fire, heart, ts, parent_id, deleted, hidden,
    parent_nick, parent_body, parent_deleted (silinmiş ya da gizlenmiş), mine."""
    post, parent_nick, parent_body, parent_deleted = row
    data = {
        "id": post.id, "room": post.room, "nick": post.nick, "body": post.body,
        "fire": post.fire, "heart": post.heart, "ts": post.ts,
        "parent_id": post.parent_id, "deleted": bool(post.deleted), "hidden": bool(post.hidden),
        "parent_nick": parent_nick, "parent_body": parent_body,
        "parent_deleted": bool(parent_deleted),
    }
    # Gizli sahiplik anahtarı API yanıtına konmaz, sadece "mine" hesaplanır
    data["mine"] = bool(owner and post.owner and hmac.compare_digest(post.owner, owner))

    if data["deleted"] or data["hidden"]:
        data["body"] = ""
    if data["parent_deleted"]:
        data["parent_body"] = ""
    elif data.get("parent_body"):
        data["parent_body"] = data["parent_body"][:90]

    return data


class Hub:
    def __init__(self):
        self.clients = set()

    async def add(self, websocket: WebSocket):
        await websocket.accept()
        self.clients.add(websocket)
        await self.send_online()

    async def drop(self, websocket: WebSocket):
        self.clients.discard(websocket)
        await self.send_online()

    async def broadcast(self, data):
        stale_clients = []
        for websocket in list(self.clients):
            try:
                await websocket.send_json(data)
            except Exception:
                stale_clients.append(websocket)
        for websocket in stale_clients:
            self.clients.discard(websocket)

    async def send_online(self):
        await self.broadcast({"type": "online", "count": len(self.clients)})


hub = Hub()


def clean(text: str) -> str:
    """Boşlukları sadeleştirir, küfürleri *** yapar (app/profanity.py)."""
    return mask(text)


class PostIn(BaseModel):
    room: str
    nick: str = Field(min_length=2, max_length=20)
    body: str = Field(min_length=1, max_length=500)
    owner: str = Field(min_length=8, max_length=64)
    parent_id: Optional[int] = None


class ReactIn(BaseModel):
    type: str


class DelIn(BaseModel):
    owner: str = Field(min_length=8, max_length=64)


class ReportIn(BaseModel):
    owner: str = Field(min_length=8, max_length=64)


report_log = {}                     # ip özeti -> son bir saatteki bildirim zamanları


def reporter_key(ip: str) -> str:
    """Bildirenin kimliği: IP'nin özeti (veritabanına IP yazılmaz)."""
    return hashlib.sha256(f"fenerhub-report:{ip}".encode()).hexdigest()


@forum_router.get("/api/forum/next-match")
def next_match():
    match = current_match()
    if not match:
        return {"room": None}
    opponent = (
        match["away"] if match["home"] == "Fenerbahçe" else match["home"]
    )
    return {
        **match,
        "room": "mac-" + match["id"],
        "opponent": opponent,
    }


@forum_router.get("/api/forum/posts")
def list_posts(room: str = "genel", limit: int = 60, owner: str = ""):
    if not valid_room(room):
        raise HTTPException(status_code=400, detail="Geçersiz oda")
    safe_limit = max(1, min(limit, 100))
    with SessionLocal() as session:
        rows = session.execute(
            SELECT_POST.where(ForumPost.room == room).order_by(ForumPost.id.desc()).limit(safe_limit)
        ).all()
    return [row_to_post(row, owner) for row in rows]


@forum_router.post("/api/forum/posts")
async def create_post(post: PostIn, request: Request):
    if not valid_room(post.room):
        raise HTTPException(status_code=400, detail="Geçersiz oda")

    ip = client_ip(request)   # Render proxy'si arkasında gerçek kullanıcı adresi (app/net.py)
    now = time.time()
    prune_last_post(now)
    if now - last_post.get(ip, 0) < POST_INTERVAL:
        raise HTTPException(status_code=429, detail="Biraz yavaş, 4 saniye bekle.")

    nick = clean(post.nick)
    body = clean(post.body)
    if len(nick) < 2:
        raise HTTPException(status_code=400, detail="Takma ad en az 2 karakter olmalı.")
    if not body:
        raise HTTPException(status_code=400, detail="Boş mesaj")

    def insert():
        with SessionLocal() as session, session.begin():
            if post.parent_id is not None:
                parent = session.get(ForumPost, post.parent_id)
                if not parent or parent.room != post.room or parent.deleted:
                    raise HTTPException(status_code=400, detail="Yanıtlanan mesaj bulunamadı.")
            new = ForumPost(room=post.room, nick=nick, body=body, ts=int(now),
                            owner=post.owner, parent_id=post.parent_id)
            session.add(new)
            session.flush()
            row = session.execute(SELECT_POST.where(ForumPost.id == new.id)).one()
            # Sözlükler oturum kapanmadan üretilir (commit sonrası nesne okunamaz)
            return row_to_post(row), row_to_post(row, post.owner)

    public, own = await run_in_threadpool(insert)
    last_post[ip] = now
    await hub.broadcast({"type": "post", "post": public})
    return own


@forum_router.post("/api/forum/posts/{pid}/delete")
async def delete_post(pid: int, data: DelIn):
    def soft_delete():
        with SessionLocal() as session, session.begin():
            post = session.get(ForumPost, pid)
            if not post:
                raise HTTPException(status_code=404, detail="Mesaj yok")
            if not post.owner or not hmac.compare_digest(post.owner, data.owner):
                raise HTTPException(status_code=403, detail="Sadece kendi mesajını silebilirsin.")
            post.deleted = True
            post.body = ""

    await run_in_threadpool(soft_delete)
    await hub.broadcast({"type": "delete", "id": pid})
    return {"ok": True}


@forum_router.post("/api/forum/posts/{pid}/report")
async def report_post(pid: int, data: ReportIn, request: Request):
    """Mesajı bildir: aynı kullanıcı (IP) bir mesajı bir kez bildirir, kendi mesajını bildiremez.
    REPORT_LIMIT farklı kullanıcı bildirince mesaj gizlenir ve herkesin ekranından kalkar."""
    who = reporter_key(client_ip(request))
    now = time.time()
    recent = [t for t in report_log.get(who, []) if now - t < 3600]
    if len(recent) >= REPORTS_PER_HOUR:
        raise HTTPException(status_code=429, detail="Çok fazla bildirim; biraz sonra tekrar dene.")

    def add_report():
        with SessionLocal() as session, session.begin():
            post = session.get(ForumPost, pid)
            if not post or post.deleted:
                raise HTTPException(status_code=404, detail="Mesaj yok")
            if post.owner and hmac.compare_digest(post.owner, data.owner):
                raise HTTPException(status_code=400, detail="Kendi mesajını bildiremezsin.")
            try:
                with session.begin_nested():
                    session.add(PostReport(post_id=pid, reporter=who, ts=int(now)))
            except IntegrityError:
                return {"ok": True, "already": True, "hidden": bool(post.hidden)}
            count = session.scalar(select(func.count()).select_from(PostReport).where(PostReport.post_id == pid))
            newly_hidden = count >= REPORT_LIMIT and not post.hidden
            if newly_hidden:
                post.hidden = True
            return {"ok": True, "already": False, "hidden": bool(post.hidden), "newly_hidden": newly_hidden}

    result = await run_in_threadpool(add_report)
    if not result.get("already"):
        report_log[who] = recent + [now]
    if result.pop("newly_hidden", False):
        await hub.broadcast({"type": "hide", "id": pid})
    return result


@forum_router.post("/api/forum/posts/{pid}/react")
async def react(pid: int, reaction: ReactIn):
    column = {"fire": "fire", "heart": "heart"}.get(reaction.type)
    if not column:
        raise HTTPException(status_code=400, detail="Geçersiz tepki")

    def increment():
        with SessionLocal() as session, session.begin():
            # Tek UPDATE ile artır: aynı anda gelen tepkiler birbirini ezmez
            col = getattr(ForumPost, column)
            result = session.execute(
                update(ForumPost).where(ForumPost.id == pid).values({column: col + 1})
            )
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="Mesaj yok")
            post = session.get(ForumPost, pid)
            session.refresh(post)
            return {"id": post.id, "fire": post.fire, "heart": post.heart}

    data = await run_in_threadpool(increment)
    await hub.broadcast({"type": "react", **data})
    return data


@forum_router.websocket("/ws/forum")
async def ws_forum(websocket: WebSocket):
    # hub.add bağlantıyı kabul eder; burada ikinci kez accept çağrılmamalı.
    await hub.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await hub.drop(websocket)
