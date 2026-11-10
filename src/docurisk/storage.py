"""Small SQLite metadata store for the single-instance alpha. No users/tenants yet."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class Store:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.uploads = self.root / "uploads"
        self.uploads.mkdir(exist_ok=True)
        self.db = self.root / "metadata.sqlite3"
        with self.connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    page_count INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    error_code TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS pages (
                    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    page_number INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    markdown TEXT NOT NULL,
                    PRIMARY KEY (document_id, page_number)
                );
            """)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db, timeout=20)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            with conn:
                yield conn
        finally:
            conn.close()

    def add(self, record: dict) -> None:
        with self.connect() as conn:
            conn.execute("""INSERT INTO documents
                (id, filename, sha256, size_bytes, page_count, status, created_at)
                VALUES (:id, :filename, :sha256, :size_bytes, :page_count, :status, :created_at)""", record)

    def get(self, doc_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
            return dict(row) if row else None

    def page(self, doc_id: str, page_number: int) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM pages WHERE document_id = ? AND page_number = ?",
                (doc_id, page_number),
            ).fetchone()
            return dict(row) if row else None

    def complete(self, doc_id: str, pages: list[dict], page_count: int) -> None:
        with self.connect() as conn:
            conn.executemany(
                "INSERT INTO pages (document_id, page_number, text, markdown) VALUES (?, ?, ?, ?)",
                [(doc_id, p["page_number"], p["text"], p["markdown"]) for p in pages],
            )
            conn.execute("UPDATE documents SET status = 'completed', page_count = ? WHERE id = ?", (page_count, doc_id))

    def set_status(self, doc_id: str, status: str, error_code: str | None = None) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE documents SET status = ?, error_code = ? WHERE id = ?", (status, error_code, doc_id))

    def delete(self, doc_id: str) -> bool:
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            return cursor.rowcount > 0
