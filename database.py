import sqlite3
from pathlib import Path

DB_DIR = Path(__file__).parent / "instance"
DB_PATH = DB_DIR / "zoffset.db"


def get_connection():
    DB_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS printers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            z_offset REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def get_printers():
    conn = get_connection()
    rows = conn.execute("SELECT id, name, z_offset FROM printers ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_printers_dict():
    printers = {}
    for i, p in enumerate(get_printers(), 1):
        printers[f"imp{i}"] = {"name": p["name"], "z_offset": p["z_offset"]}
    return printers


def add_printer(name, z_offset):
    conn = get_connection()
    conn.execute("INSERT INTO printers (name, z_offset) VALUES (?, ?)", (name, z_offset))
    conn.commit()
    conn.close()


def update_printer(printer_id, name, z_offset):
    conn = get_connection()
    conn.execute("UPDATE printers SET name = ?, z_offset = ? WHERE id = ?", (name, z_offset, printer_id))
    conn.commit()
    conn.close()


def delete_printer(printer_id):
    conn = get_connection()
    conn.execute("DELETE FROM printers WHERE id = ?", (printer_id,))
    conn.commit()
    conn.close()


def seed_from_json_if_empty():
    """Se o banco estiver vazio, tenta carregar do printers.json (migração)."""
    from pathlib import Path
    import json

    printers = get_printers()
    if printers:
        return

    json_path = Path(__file__).parent / "printers.json"
    if not json_path.exists():
        return

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    conn = get_connection()
    for info in data.values():
        conn.execute(
            "INSERT INTO printers (name, z_offset) VALUES (?, ?)",
            (info["name"], info["z_offset"]),
        )
    conn.commit()
    conn.close()
