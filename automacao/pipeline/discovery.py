"""Discovery: busca vagas nas fontes do catálogo (config/sources.yaml) e grava no SQLite via db.py.

Regra: feed/API é o padrão, parser de HTML é fallback.
Cada fonte respeita o próprio poll_interval_hours — não existe cron global único.
"""

import hashlib
import re
from datetime import datetime, timedelta, timezone

import feedparser
import requests
import yaml

from automacao import db

CONFIG_DIR = __import__("pathlib").Path(__file__).parent.parent / "config"


def load_sources() -> list[dict]:
    with open(CONFIG_DIR / "sources.yaml") as f:
        return yaml.safe_load(f)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dedup_key(company: str, title: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", f"{company}-{title}".lower()).strip("-")
    return hashlib.sha256(normalized.encode()).hexdigest()[:24]


def _due_for_poll(source: dict) -> bool:
    last_polled = db.get_source_last_polled(source["id"])
    if last_polled is None:
        return True
    elapsed = datetime.now(timezone.utc) - datetime.fromisoformat(last_polled)
    return elapsed >= timedelta(hours=source["poll_interval_hours"])


def fetch_rss(source: dict) -> list[dict]:
    feed = feedparser.parse(source["url"])
    jobs = []
    for entry in feed.entries:
        company = getattr(entry, "author", "").strip() or "desconhecido"
        title = entry.title
        jobs.append({
            "dedup_key": _dedup_key(company, title),
            "source": source["id"],
            "company": company,
            "title": title,
            "url": entry.link,
            "description": getattr(entry, "summary", ""),
            "remote_modality": "remoto",  # categoria já filtra "remote-programming-jobs"
            "candidate_required_location": None,
            "visa_or_contractor_note": None,
        })
    return jobs


def fetch_api_remotive(source: dict) -> list[dict]:
    response = requests.get(source["url"], timeout=30)
    response.raise_for_status()
    jobs = []
    for item in response.json().get("jobs", []):
        jobs.append({
            "dedup_key": _dedup_key(item["company_name"], item["title"]),
            "source": source["id"],
            "company": item["company_name"],
            "title": item["title"],
            "url": item["url"],
            "description": item.get("description", ""),
            "remote_modality": "remoto",
            "candidate_required_location": item.get("candidate_required_location"),
            "visa_or_contractor_note": None,
        })
    return jobs


# TODO: fetch_api_remoteok — status "inconclusivo" em sources.yaml. Antes de habilitar,
# testar remoteok.com/api com header de User-Agent explícito (deu 403 sem header no teste manual).
FETCHERS = {
    "weworkremotely-programming": fetch_rss,
    "remotive-api": fetch_api_remotive,
}


def run_discovery() -> list[int]:
    """Busca todas as fontes cujo poll_interval já venceu. Retorna os ids das vagas novas/atualizadas."""
    job_ids = []
    for source in load_sources():
        if source.get("status") == "inconclusivo":
            continue
        if not _due_for_poll(source):
            continue

        fetcher = FETCHERS.get(source["id"])
        if fetcher is None:
            continue  # fonte catalogada mas sem parser implementado ainda

        now_iso = _now_iso()
        for job in fetcher(source):
            job_ids.append(db.upsert_job(job, now_iso))
        db.set_source_last_polled(source["id"], now_iso)

    return job_ids
