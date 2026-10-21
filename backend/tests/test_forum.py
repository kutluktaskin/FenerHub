"""Forum (12. Adam) uç noktaları: SQLAlchemy geçişinden sonra davranış ve cevap biçimi aynı kalmalı."""
import asyncio

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app import forum
from app.database import engine

OWNER = "test-owner-12345"
FIELDS = {"id", "room", "nick", "body", "fire", "heart", "ts", "parent_id", "deleted", "hidden",
          "parent_nick", "parent_body", "parent_deleted", "mine"}


def req(ip):
    return Request({"type": "http", "method": "POST", "path": "/", "client": ("10.0.0.5", 1),
                    "headers": [(b"x-forwarded-for", ip.encode())]})


def post(body, ip="88.230.1.2", owner=OWNER, parent_id=None, room="genel", nick="testci"):
    data = forum.PostIn(room=room, nick=nick, body=body, owner=owner, parent_id=parent_id)
    return asyncio.run(forum.create_post(data, req(ip)))


def test_database_is_temporary():
    assert "fenerhub-test-" in str(engine.url)


def test_create_and_list_same_shape():
    created = post("Haydi Fener!")
    assert set(created) == FIELDS and created["mine"] is True and created["deleted"] is False
    listed = forum.list_posts(room="genel", owner=OWNER)
    assert listed[0]["id"] == created["id"] and set(listed[0]) == FIELDS
    assert forum.list_posts(room="genel")[0]["mine"] is False      # sahiplik anahtarı olmadan


def test_rate_limit_per_ip():
    post("ilk", ip="1.2.3.4")
    with pytest.raises(HTTPException) as e:
        post("ikinci", ip="1.2.3.4")
    assert e.value.status_code == 429
    post("başka kullanıcı", ip="5.6.7.8")                           # başkası kilitlenmez


def test_reply_react_delete():
    parent = post("ana mesaj", ip="9.9.9.1")
    reply = post("yanıt", ip="9.9.9.2", owner="diger-owner-999", parent_id=parent["id"])
    assert reply["parent_nick"] == "testci" and reply["parent_body"] == "ana mesaj"

    asyncio.run(forum.react(parent["id"], forum.ReactIn(type="fire")))
    counts = asyncio.run(forum.react(parent["id"], forum.ReactIn(type="fire")))
    assert counts == {"id": parent["id"], "fire": 2, "heart": 0}

    with pytest.raises(HTTPException) as e:
        asyncio.run(forum.delete_post(parent["id"], forum.DelIn(owner="yanlis-owner-000")))
    assert e.value.status_code == 403
    asyncio.run(forum.delete_post(parent["id"], forum.DelIn(owner=OWNER)))

    rows = {p["id"]: p for p in forum.list_posts(room="genel")}
    assert rows[parent["id"]]["deleted"] is True and rows[parent["id"]]["body"] == ""
    assert rows[reply["id"]]["parent_deleted"] is True and rows[reply["id"]]["parent_body"] == ""


def test_invalid_room_and_missing_post():
    with pytest.raises(HTTPException) as e:
        forum.list_posts(room="yok")
    assert e.value.status_code == 400
    with pytest.raises(HTTPException) as e:
        asyncio.run(forum.react(999_999, forum.ReactIn(type="heart")))
    assert e.value.status_code == 404


def report(pid, ip, owner="baskasi-123456"):
    return asyncio.run(forum.report_post(pid, forum.ReportIn(owner=owner), req(ip)))


def test_report_hides_after_three_different_users(monkeypatch):
    sent = []

    async def fake_broadcast(data):
        sent.append(data)
    monkeypatch.setattr(forum.hub, "broadcast", fake_broadcast)
    forum.report_log.clear()
    pid = post("bildirilecek mesaj", ip="88.230.9.1")["id"]

    with pytest.raises(HTTPException) as e:                 # kendi mesajını bildiremez
        report(pid, "88.230.9.2", owner=OWNER)
    assert e.value.status_code == 400

    assert report(pid, "88.230.9.3")["hidden"] is False
    assert report(pid, "88.230.9.3")["already"] is True       # aynı kullanıcı ikinci kez sayılmaz
    assert report(pid, "88.230.9.4")["hidden"] is False
    assert report(pid, "88.230.9.5")["hidden"] is True        # 3. farklı kullanıcı: gizlendi
    assert {"type": "hide", "id": pid} in sent

    listed = [p for p in forum.list_posts("genel", 100, "") if p["id"] == pid][0]
    assert listed["hidden"] is True and listed["body"] == ""

    with pytest.raises(HTTPException):
        report(999999, "88.230.9.7")                          # olmayan mesaj: 404


def test_report_rate_limit(monkeypatch):
    async def fake_broadcast(data):
        pass
    monkeypatch.setattr(forum.hub, "broadcast", fake_broadcast)
    forum.report_log.clear()
    monkeypatch.setattr(forum, "REPORTS_PER_HOUR", 2)
    ids = [post(f"m{i}", ip=f"88.230.8.{i}")["id"] for i in range(3)]
    report(ids[0], "88.230.7.1")
    report(ids[1], "88.230.7.1")
    with pytest.raises(HTTPException) as e:
        report(ids[2], "88.230.7.1")
    assert e.value.status_code == 429


def test_profanity_filter_in_posts():
    created = post("s.i.k.t.i.r hakem, topu götür!", ip="88.230.6.1")
    assert created["body"] == "*** hakem, topu götür!"
