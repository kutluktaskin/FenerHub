import re, sqlite3, time, hmac
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from datetime import datetime, timedelta, timezone

DB = Path(__file__).parent / "forum.db"
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
    for m in FIXTURES:
        kickoff = datetime.fromisoformat(m["kickoff"])
        if now < kickoff + MATCH_LENGTH + KEEP_OPEN:
            return m
    return None

def valid_room(room: str) -> bool:
    return room in ROOMS or room in {"mac-" + m["id"] for m in FIXTURES}

BAD = ["küfür1", "küfür2"]          # kendi yasaklı kelimelerini ekle
last_post = {}                      # ip -> son mesaj zamanı

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

with db() as c:
    c.execute("""CREATE TABLE IF NOT EXISTS posts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room TEXT NOT NULL, nick TEXT NOT NULL, body TEXT NOT NULL,
        fire INTEGER DEFAULT 0, heart INTEGER DEFAULT 0, ts INTEGER NOT NULL)""")
    cols = {r[1] for r in c.execute("PRAGMA table_info(posts)")}
    if "owner" not in cols:
        c.execute("ALTER TABLE posts ADD COLUMN owner TEXT")
    if "parent_id" not in cols:
        c.execute("ALTER TABLE posts ADD COLUMN parent_id INTEGER")
    if "deleted" not in cols:
        c.execute("ALTER TABLE posts ADD COLUMN deleted INTEGER DEFAULT 0")

SELECT_POST = """
SELECT p.id, p.room, p.nick, p.body, p.fire, p.heart, p.ts,
       p.parent_id, p.deleted, p.owner,
       q.nick AS parent_nick, q.body AS parent_body, q.deleted AS parent_deleted
FROM posts p LEFT JOIN posts q ON q.id = p.parent_id
"""

def row_to_post(r, owner: str = ""):
    d = dict(r)
    own = d.pop("owner", None)          # kimlik asla istemciye gönderilmez
    d["mine"] = bool(owner and own and hmac.compare_digest(own, owner))
    d["deleted"] = bool(d.get("deleted"))
    d["parent_deleted"] = bool(d.get("parent_deleted"))
    if d["deleted"]:
        d["body"] = ""
    if d["parent_deleted"]:
        d["parent_body"] = ""
    elif d.get("parent_body"):
        d["parent_body"] = d["parent_body"][:90]
    return d

class Hub:
    def __init__(self): self.clients = set()
    async def add(self, ws):
        await ws.accept(); self.clients.add(ws); await self.send_online()
    async def drop(self, ws):
        self.clients.discard(ws); await self.send_online()
    async def broadcast(self, data):
        for ws in list(self.clients):
            try: await ws.send_json(data)
            except Exception: self.clients.discard(ws)
    async def send_online(self):
        await self.broadcast({"type": "online", "count": len(self.clients)})

hub = Hub()

def clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    for w in BAD:
        text = re.sub(re.escape(w), "***", text, flags=re.I)
    return text

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

@app.get("/api/forum/next-match")
def next_match():
    m = current_match()
    if not m:
        return {"room": None}
    opp = m["away"] if m["home"] == "Fenerbahçe" else m["home"]
    return {**m, "room": "mac-" + m["id"], "opponent": opp}

@app.get("/api/forum/posts")
def list_posts(room: str = "genel", limit: int = 60, owner: str = ""):
    if not valid_room(room): raise HTTPException(400, "Geçersiz oda")
    with db() as c:
        rows = c.execute(SELECT_POST + " WHERE p.room=? ORDER BY p.id DESC LIMIT ?",
                         (room, min(limit, 100))).fetchall()
    return [row_to_post(r, owner) for r in rows]

@app.post("/api/forum/posts")
async def create_post(p: PostIn, req: Request):
    if not valid_room(p.room): raise HTTPException(400, "Geçersiz oda")
    ip = req.client.host
    if time.time() - last_post.get(ip, 0) < 4:
        raise HTTPException(429, "Biraz yavaş, 4 saniye bekle.")
    nick, body = clean(p.nick), clean(p.body)
    if not body: raise HTTPException(400, "Boş mesaj")
    with db() as c:
        if p.parent_id:
            par = c.execute("SELECT room, deleted FROM posts WHERE id=?", (p.parent_id,)).fetchone()
            if not par or par["room"] != p.room or par["deleted"]:
                raise HTTPException(400, "Yanıtlanan mesaj bulunamadı.")
        last_post[ip] = time.time()
        cur = c.execute(
            "INSERT INTO posts(room,nick,body,ts,owner,parent_id) VALUES(?,?,?,?,?,?)",
            (p.room, nick, body, int(time.time()), p.owner, p.parent_id))
        row = c.execute(SELECT_POST + " WHERE p.id=?", (cur.lastrowid,)).fetchone()
    await hub.broadcast({"type": "post", "post": row_to_post(row)})
    return row_to_post(row, p.owner)

@app.post("/api/forum/posts/{pid}/delete")
async def delete_post(pid: int, d: DelIn):
    with db() as c:
        row = c.execute("SELECT owner FROM posts WHERE id=?", (pid,)).fetchone()
        if not row: raise HTTPException(404, "Mesaj yok")
        if not row["owner"] or not hmac.compare_digest(row["owner"], d.owner):
            raise HTTPException(403, "Sadece kendi mesajını silebilirsin.")
        c.execute("UPDATE posts SET deleted=1, body='' WHERE id=?", (pid,))
    await hub.broadcast({"type": "delete", "id": pid})
    return {"ok": True}

@app.post("/api/forum/posts/{pid}/react")
async def react(pid: int, r: ReactIn):
    col = {"fire": "fire", "heart": "heart"}.get(r.type)
    if not col: raise HTTPException(400, "Geçersiz tepki")
    with db() as c:
        c.execute(f"UPDATE posts SET {col}={col}+1 WHERE id=?", (pid,))
        row = c.execute("SELECT id,fire,heart FROM posts WHERE id=?", (pid,)).fetchone()
    if not row: raise HTTPException(404, "Mesaj yok")
    await hub.broadcast({"type": "react", **dict(row)})
    return dict(row)

@app.websocket("/ws/forum")
async def ws_forum(ws: WebSocket):
    await hub.add(ws)
    try:
        while True: await ws.receive_text()
    except WebSocketDisconnect:
        await hub.drop(ws)