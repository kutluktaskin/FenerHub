"""Testler gerçek veritabanına dokunmaz: her oturumda boş, geçici bir SQLite kullanılır.
DATABASE_URL, app paketi import edilmeden önce ayarlanmalı (app/database.py import anında okur)."""
import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="fenerhub-test-")) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.as_posix()}"

import pytest  # noqa: E402

from app.migrate import run_migrations  # noqa: E402

run_migrations()


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from app import forum
    forum.last_post.clear()
    yield
