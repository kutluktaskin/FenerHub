"""Testler gerçek veritabanına ve SportsAPI'ye dokunmaz:
- her oturumda boş, geçici bir SQLite kullanılır (DATABASE_URL, app paketi import edilmeden önce
  ayarlanmalı; app/database.py import anında okur)
- her türlü HTTP isteği engellenir: günlük API kotası testlerde harcanmasın. Ağ gerektiren
  kod sync.api_get'i sahte bir fonksiyonla değiştirerek test edilir."""
import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="fenerhub-test-")) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.as_posix()}"

import pytest  # noqa: E402
import requests  # noqa: E402

from app.migrate import run_migrations  # noqa: E402

run_migrations()


class NetworkBlocked(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise NetworkBlocked("Testlerde ağ isteği yasak (kota korunur); sync.api_get'i sahtele")
    monkeypatch.setattr(requests, "get", blocked)
    monkeypatch.setattr(requests.Session, "request", blocked)
    yield


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from app import forum
    forum.last_post.clear()
    yield
