"""Camada de acesso a dados compartilhada.

Toda leitura/escrita no SQLite passa por aqui — nunca SQL solto no pipeline ou no dashboard.
Funções puras: recebem/retornam dict/list/str/int, sem nada acoplado ao Streamlit.
Sem pandas: volume de dados (dezenas/centenas de vagas) não justifica DataFrame.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "jobs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    last_polled_at TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dedup_key TEXT UNIQUE NOT NULL,      -- empresa+titulo normalizado, ou hash da URL de candidatura
    source TEXT NOT NULL,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    description TEXT,
    remote_modality TEXT,                -- remoto | hibrido | presencial | desconhecido
    candidate_required_location TEXT,
    visa_or_contractor_note TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job_keywords (
    job_id INTEGER NOT NULL REFERENCES jobs(id),
    keyword TEXT NOT NULL,
    category TEXT,                       -- categoria da role_taxonomy (ex: Backend, Warehouses)
    PRIMARY KEY (job_id, keyword)
);

CREATE TABLE IF NOT EXISTS job_scores (
    job_id INTEGER NOT NULL REFERENCES jobs(id),
    profile_id TEXT NOT NULL,
    score REAL NOT NULL,
    notified INTEGER NOT NULL DEFAULT 0, -- 0/1 — já disparou e-mail para este profile?
    scored_at TEXT NOT NULL,
    PRIMARY KEY (job_id, profile_id)
);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES jobs(id),
    profile_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'found', -- found | cv_gerado | enviada | entrevista | rejeitada | oferta
    cv_path TEXT,
    submitted_at TEXT,
    notes TEXT
);
"""


@contextmanager
def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(SCHEMA)


# --- sources -----------------------------------------------------------

def get_source_last_polled(source_id: str) -> str | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT last_polled_at FROM sources WHERE id = ?", (source_id,)
        ).fetchone()
        return row["last_polled_at"] if row else None


def set_source_last_polled(source_id: str, timestamp_iso: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO sources (id, last_polled_at) VALUES (?, ?) "
            "ON CONFLICT(id) DO UPDATE SET last_polled_at = excluded.last_polled_at",
            (source_id, timestamp_iso),
        )


# --- jobs ----------------------------------------------------------------

def upsert_job(job: dict, now_iso: str) -> int:
    """Insere a vaga se for nova (por dedup_key); se já existir, só atualiza last_seen.

    `job` deve conter: dedup_key, source, company, title, url, description,
    remote_modality, candidate_required_location, visa_or_contractor_note.
    Retorna o id da vaga (nova ou existente).
    """
    with _connect() as conn:
        existing = conn.execute(
            "SELECT id FROM jobs WHERE dedup_key = ?", (job["dedup_key"],)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE jobs SET last_seen = ? WHERE id = ?", (now_iso, existing["id"])
            )
            return existing["id"]

        cursor = conn.execute(
            """INSERT INTO jobs
               (dedup_key, source, company, title, url, description, remote_modality,
                candidate_required_location, visa_or_contractor_note, first_seen, last_seen)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job["dedup_key"], job["source"], job["company"], job["title"], job["url"],
                job.get("description", ""), job.get("remote_modality", "desconhecido"),
                job.get("candidate_required_location"), job.get("visa_or_contractor_note"),
                now_iso, now_iso,
            ),
        )
        return cursor.lastrowid


def set_job_keywords(job_id: int, keywords: list[tuple[str, str]]) -> None:
    """`keywords` é uma lista de (keyword, category) já resolvida por matching contra a role_taxonomy."""
    with _connect() as conn:
        conn.execute("DELETE FROM job_keywords WHERE job_id = ?", (job_id,))
        conn.executemany(
            "INSERT INTO job_keywords (job_id, keyword, category) VALUES (?, ?, ?)",
            [(job_id, kw, cat) for kw, cat in keywords],
        )


def list_jobs(profile_id: str | None = None, min_score: float | None = None) -> list[dict]:
    query = """
        SELECT j.*, s.score, s.profile_id
        FROM jobs j
        LEFT JOIN job_scores s ON s.job_id = j.id
        WHERE 1=1
    """
    params: list = []
    if profile_id:
        query += " AND s.profile_id = ?"
        params.append(profile_id)
    if min_score is not None:
        query += " AND s.score >= ?"
        params.append(min_score)
    query += " ORDER BY s.score DESC"

    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


# --- scoring ---------------------------------------------------------------

def upsert_score(job_id: int, profile_id: str, score: float, now_iso: str) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO job_scores (job_id, profile_id, score, scored_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(job_id, profile_id) DO UPDATE SET
                 score = excluded.score, scored_at = excluded.scored_at""",
            (job_id, profile_id, score, now_iso),
        )


def list_pending_notifications(profile_id: str, threshold: float) -> list[dict]:
    """Vagas que cruzaram o threshold do profile e ainda não geraram e-mail."""
    with _connect() as conn:
        rows = conn.execute(
            """SELECT j.*, s.score
               FROM jobs j
               JOIN job_scores s ON s.job_id = j.id
               WHERE s.profile_id = ? AND s.score >= ? AND s.notified = 0""",
            (profile_id, threshold),
        ).fetchall()
        return [dict(row) for row in rows]


def mark_notified(job_id: int, profile_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE job_scores SET notified = 1 WHERE job_id = ? AND profile_id = ?",
            (job_id, profile_id),
        )


# --- gap analysis (agregação determinística, sem LLM/pandas) --------------

def keyword_gap(profile_id: str, candidate_keywords: set[str]) -> list[dict]:
    """Frequência de cada keyword nas vagas pontuadas do profile, marcando se falta no candidato.

    Retorna lista de {keyword, category, frequency, missing} ordenada por frequência desc.
    """
    with _connect() as conn:
        rows = conn.execute(
            """SELECT jk.keyword, jk.category, COUNT(DISTINCT jk.job_id) AS frequency
               FROM job_keywords jk
               JOIN job_scores s ON s.job_id = jk.job_id
               WHERE s.profile_id = ?
               GROUP BY jk.keyword, jk.category
               ORDER BY frequency DESC""",
            (profile_id,),
        ).fetchall()
        return [
            {
                "keyword": row["keyword"],
                "category": row["category"],
                "frequency": row["frequency"],
                "missing": row["keyword"].lower() not in {k.lower() for k in candidate_keywords},
            }
            for row in rows
        ]


# --- applications (tracking de candidatura) ---------------------------------

def create_application(job_id: int, profile_id: str) -> int:
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO applications (job_id, profile_id, status) VALUES (?, ?, 'found')",
            (job_id, profile_id),
        )
        return cursor.lastrowid


def update_application_status(application_id: int, status: str, **fields) -> None:
    """`fields` aceita cv_path, submitted_at, notes."""
    allowed = {"cv_path", "submitted_at", "notes"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    set_clause = ", ".join(f"{k} = ?" for k in ["status", *updates.keys()])
    with _connect() as conn:
        conn.execute(
            f"UPDATE applications SET {set_clause} WHERE id = ?",
            (status, *updates.values(), application_id),
        )


def list_applications(profile_id: str | None = None) -> list[dict]:
    query = "SELECT a.*, j.company, j.title, j.url FROM applications a JOIN jobs j ON j.id = a.job_id"
    params: list = []
    if profile_id:
        query += " WHERE a.profile_id = ?"
        params.append(profile_id)
    query += " ORDER BY a.id DESC"
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]
