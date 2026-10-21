"""Run a .sql file against the database (works on Windows without psql).

Usage (from the backend folder):
    python scripts/apply_sql.py ../db/migrations/002_reviews.sql
"""
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()

if len(sys.argv) != 2:
    sys.exit("Usage: python scripts/apply_sql.py <file.sql>")
sql = Path(sys.argv[1]).read_text(encoding="utf-8")
with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    conn.execute(sql)
print(f"Applied {sys.argv[1]}")
