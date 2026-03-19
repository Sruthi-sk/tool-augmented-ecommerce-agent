"""
Export partselect_index.db tables to CSV files for easy inspection.

Usage:
    cd backend
    python export_db_to_csv.py

Writes one CSV per table into backend/csv_export/.
"""
import csv
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "partselect_index.db")
OUT_DIR = os.path.join(os.path.dirname(__file__), "csv_export")

TABLES = [
    "parts",
    "models",
    "part_compatibility",
    "part_installation_steps",
    "part_symptoms",
    "troubleshooting_causes",
    "help_chunks",
]

os.makedirs(OUT_DIR, exist_ok=True)

con = sqlite3.connect(DB_PATH)
con.row_factory = sqlite3.Row

for table in TABLES:
    try:
        cur = con.execute(f"SELECT * FROM {table}")
        rows = cur.fetchall()
        out_path = os.path.join(OUT_DIR, f"{table}.csv")
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(rows[0].keys() if rows else [])
            writer.writerows(rows)
        print(f"  {table}: {len(rows)} rows → csv_export/{table}.csv")
    except Exception as e:
        print(f"  {table}: skipped ({e})")

con.close()
print(f"\nDone. Files in: {OUT_DIR}")
