        connection.execute("ALTER TABLE posts ADD COLUMN owner TEXT")
    if "parent_id" not in columns:
        connection.execute("ALTER TABLE posts ADD COLUMN parent_id INTEGER")
    if "deleted" not in columns:
        connection.execute("ALTER TABLE posts ADD COLUMN deleted INTEGER DEFAULT 0")


SELECT_POST = """
SELECT p.id, p.room, p.nick, p.body, p.fire, p.heart, p.ts,
       p.parent_id, p.deleted, p.owner,
       q.nick AS parent_nick, q.body AS parent_body, q.deleted AS parent_deleted
FROM posts p LEFT JOIN posts q ON q.id = p.parent_id
"""


def row_to_post(row, owner: str = ""):
    data = dict(row)
    post_owner = data.pop("owner", None)  # Gizli sahiplik anahtarı API yanıtına konmaz.
    data["mine"] = bool(
        owner and post_owner and hmac.compare_digest(post_owner, owner)
    )
    data["deleted"] = bool(data.get("deleted"))
    data["parent_deleted"] = bool(data.get("parent_deleted"))

    if data["deleted"]:
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
    text = re.sub(r"\s+", " ", text).strip()
    for word in BAD:
        text = re.sub(re.escape(word), "***", text, flags=re.IGNORECASE)
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
    with db() as connection:
        rows = connection.execute(
            SELECT_POST + " WHERE p.room=? ORDER BY p.id DESC LIMIT ?",
            (room, safe_limit),
        ).fetchall()
    return [row_to_post(row, owner) for row in rows]


@forum_router.post("/api/forum/posts")
async def create_post(post: PostIn, request: Request):
    if not valid_room(post.room):
        raise HTTPException(status_code=400, detail="Geçersiz oda")

    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    if now - last_post.get(client_ip, 0) < 4:
        raise HTTPException(status_code=429, detail="Biraz yavaş, 4 saniye bekle.")

    nick = clean(post.nick)
    body = clean(post.body)
    if len(nick) < 2:
        raise HTTPException(status_code=400, detail="Takma ad en az 2 karakter olmalı.")
    if not body:
        raise HTTPException(status_code=400, detail="Boş mesaj")

    with db() as connection:
        if post.parent_id is not None:
            parent = connection.execute(
                "SELECT room, deleted FROM posts WHERE id=?", (post.parent_id,)
            ).fetchone()
            if not parent or parent["room"] != post.room or parent["deleted"]:
                raise HTTPException(
                    status_code=400, detail="Yanıtlanan mesaj bulunamadı."
                )

        cursor = connection.execute(
            "INSERT INTO posts(room,nick,body,ts,owner,parent_id) VALUES(?,?,?,?,?,?)",
            (post.room, nick, body, int(now), post.owner, post.parent_id),
        )
        row = connection.execute(
            SELECT_POST + " WHERE p.id=?", (cursor.lastrowid,)
        ).fetchone()

    last_post[client_ip] = now
    await hub.broadcast({"type": "post", "post": row_to_post(row)})
    return row_to_post(row, post.owner)


@forum_router.post("/api/forum/posts/{pid}/delete")
async def delete_post(pid: int, data: DelIn):
    with db() as connection:
        row = connection.execute(
            "SELECT owner FROM posts WHERE id=?", (pid,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Mesaj yok")
        if not row["owner"] or not hmac.compare_digest(row["owner"], data.owner):
            raise HTTPException(
                status_code=403,
                detail="Sadece kendi mesajını silebilirsin.",
            )
        connection.execute(
            "UPDATE posts SET deleted=1, body='' WHERE id=?", (pid,)
        )

    await hub.broadcast({"type": "delete", "id": pid})
    return {"ok": True}


@forum_router.post("/api/forum/posts/{pid}/react")
async def react(pid: int, reaction: ReactIn):
    column = {"fire": "fire", "heart": "heart"}.get(reaction.type)
    if not column:
        raise HTTPException(status_code=400, detail="Geçersiz tepki")

    with db() as connection:
        row = connection.execute(
            "SELECT id FROM posts WHERE id=?", (pid,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Mesaj yok")
        connection.execute(
            f"UPDATE posts SET {column}={column}+1 WHERE id=?", (pid,)
        )
        updated = connection.execute(