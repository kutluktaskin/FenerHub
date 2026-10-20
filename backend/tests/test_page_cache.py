"""Maç listesi önbelleği: yenileme başarısız olunca eski sayfa silinmemeli (takım renkleri
ve logo eşlemesi bu sayfalardan okunur; eskiden API hatasında hepsi kayboluyordu)."""
import time

import pytest
import requests

from app import auto_sync, cache, sync

OLD = [{"id": 1, "homeTeam": {"name": "Eski"}}]
NEW = [{"id": 2, "homeTeam": {"name": "Yeni"}}]
PAGES = ("pages:next_0", "pages:next_1", "pages:last_0")


@pytest.fixture
def pages(monkeypatch):
    """next_0 ve last_0 önbellekte, 5 dakikalık (yenilenmesi gerekiyor); next_1 boş."""
    for key in PAGES:
        cache.delete(key)
    cache.put("pages:next_0", OLD, fetched_at=time.time() - 300)
    cache.put("pages:last_0", OLD, fetched_at=time.time() - 300)
    monkeypatch.setattr(sync, "OFFLINE", False)
    monkeypatch.setattr(sync, "sync_matches", lambda db, events: None)   # veritabanına yazma
    yield
    for key in PAGES:
        cache.delete(key)


def fail(path):
    raise requests.exceptions.HTTPError("429 Too Many Requests")


def test_failed_refresh_keeps_old_page(pages, monkeypatch):
    monkeypatch.setattr(sync, "api_get", fail)
    auto_sync.refresh_matches(full=True)
    assert cache.get("pages:next_0") == OLD
    assert cache.get("pages:last_0") == OLD


def test_network_error_keeps_old_page(pages, monkeypatch):
    def down(path):
        raise requests.exceptions.ConnectionError("bağlantı yok")
    monkeypatch.setattr(sync, "api_get", down)
    events = sync.fetch_events(refresh=["next_0", "last_0"])
    assert cache.get("pages:next_0") == OLD
    assert [e["id"] for e in events] == [1]           # eski sayfa kullanılmaya devam eder


def test_successful_refresh_replaces_page(pages, monkeypatch):
    calls = []

    def ok(path):
        calls.append(path)
        return {"data": {"events": NEW if path.endswith("next/0") else []}}
    monkeypatch.setattr(sync, "api_get", ok)
    auto_sync.refresh_matches(full=False)
    assert cache.get("pages:next_0") == NEW
    assert cache.age("pages:next_0") < 5
    assert "/teams/3052/events/last/0" not in calls   # full=False: last_0 istenmez
    assert cache.get("pages:last_0") == OLD


def test_fresh_page_is_not_requested(pages, monkeypatch):
    cache.put("pages:next_0", OLD)                    # az önce çekildi
    calls = []
    monkeypatch.setattr(sync, "api_get", lambda p: calls.append(p) or {"data": {"events": []}})
    auto_sync.refresh_matches(full=False)
    assert "/teams/3052/events/next/0" not in calls
    assert cache.get("pages:next_0") == OLD
