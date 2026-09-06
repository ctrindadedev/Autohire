"""Scoring determinístico — sem LLM em nenhuma etapa.

Keyword matching por regex contra a role_taxonomy do profile + pesos declarados em
config/profiles/*.yaml. Resultado grava em job_scores via db.py e alimenta a gap analysis.

config/profiles/ é 100% gitignorado (e-mail/paths pessoais) — crie o seu <id>.yaml localmente
antes de rodar o pipeline. Formato documentado no README.md, seção "Automation Setup".
"""

import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

from automacao import db

CONFIG_DIR = Path(__file__).parent.parent / "config"


def load_profile(profile_id: str) -> dict:
    with open(CONFIG_DIR / "profiles" / f"{profile_id}.yaml") as f:
        return yaml.safe_load(f)


def load_all_profiles() -> list[dict]:
    """Carrega só perfis reais (`<id>.yaml`) — ignora `*.example.yaml`, que é só template versionado."""
    return [
        yaml.safe_load(path.read_text())
        for path in (CONFIG_DIR / "profiles").glob("*.yaml")
        if not path.name.endswith(".example.yaml")
    ]


def load_taxonomy(name: str) -> dict[str, list[str]]:
    with open(CONFIG_DIR / "taxonomies" / f"{name}.yaml") as f:
        return yaml.safe_load(f)


def extract_keywords(text: str, taxonomy: dict[str, list[str]]) -> list[tuple[str, str]]:
    """Retorna [(keyword, category), ...] encontrados em `text` por match de palavra inteira,
    case-insensitive. Determinístico — sem LLM."""
    found = []
    for category, keywords in taxonomy.items():
        for keyword in keywords:
            pattern = r"\b" + re.escape(keyword) + r"\b"
            if re.search(pattern, text, re.IGNORECASE):
                found.append((keyword, category))
    return found


def load_candidate_keywords(profile: dict) -> set[str]:
    """TODO: depende de cv-base.yaml como fonte estruturada. Enquanto o cv-base continuar
    só em HTML, retorna vazio — stack_overlap fica sempre 0 até isso ser resolvido.
    Não fazer parsing de HTML aqui."""
    return set()


def _score_remote_modality(job: dict) -> float:
    return 1.0 if job.get("remote_modality") == "remoto" else 0.3


def _score_stack_overlap(job_keywords: list[tuple[str, str]], candidate_keywords: set[str]) -> float:
    if not job_keywords:
        return 0.0
    candidate_lower = {k.lower() for k in candidate_keywords}
    matched = sum(1 for kw, _ in job_keywords if kw.lower() in candidate_lower)
    return matched / len(job_keywords)


def _score_company_size(job: dict) -> float:
    # TODO: sem sinal de porte de empresa implementado ainda. Neutro por enquanto —
    # não penaliza nem favorece.
    return 0.5


def score_job(job: dict, profile: dict, taxonomy: dict[str, list[str]]) -> tuple[float, list[tuple[str, str]]]:
    """Retorna (score final 0-1, keywords encontradas na vaga) para um profile."""
    text = f"{job.get('title', '')} {job.get('description', '')}"
    job_keywords = extract_keywords(text, taxonomy)
    candidate_keywords = load_candidate_keywords(profile)

    weights = profile["scoring_weights"]
    score = (
        weights.get("remote_modality", 0) * _score_remote_modality(job)
        + weights.get("stack_overlap", 0) * _score_stack_overlap(job_keywords, candidate_keywords)
        + weights.get("company_size_signal", 0) * _score_company_size(job)
    )
    return score, job_keywords


def score_all_pending(job_ids: list[int]) -> None:
    """Pontua as vagas recém-descobertas para todos os profiles cujas `sources` incluem a fonte da vaga."""
    now_iso = datetime.now(timezone.utc).isoformat()
    profiles = load_all_profiles()
    taxonomies_cache: dict[str, dict] = {}

    for job in db.list_jobs():
        if job["id"] not in job_ids:
            continue
        for profile in profiles:
            if job["source"] not in profile.get("sources", []):
                continue
            taxonomy_name = profile["role_taxonomy"]
            if taxonomy_name not in taxonomies_cache:
                taxonomies_cache[taxonomy_name] = load_taxonomy(taxonomy_name)

            score, job_keywords = score_job(job, profile, taxonomies_cache[taxonomy_name])
            db.upsert_score(job["id"], profile["id"], score, now_iso)
            db.set_job_keywords(job["id"], job_keywords)
