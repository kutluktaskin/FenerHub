from sqlalchemy import text
from app.database import engine

with engine.begin() as c:
    cols = [r[1] for r in c.execute(text("PRAGMA table_info(matches)"))]
    if "api_id" not in cols:
        c.execute(text("ALTER TABLE matches ADD COLUMN api_id INTEGER"))
        print("Eklendi: api_id")
print("Tamam")