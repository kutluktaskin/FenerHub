import sqlite3

conn = sqlite3.connect("fenerbahce.db")
rows = conn.execute(
    "select name from sqlite_master where type='table'"
).fetchall()

for row in rows:
    print(row[0])