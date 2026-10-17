import sqlite3

conn = sqlite3.connect("fenerbahce.db")
for table in ["teams", "players", "player_stats", "matches", "absences", "standings"]:
    count = conn.execute(f"select count(*) from {table}").fetchone()[0]
    print(table, count)