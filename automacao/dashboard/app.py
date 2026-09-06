"""Dashboard Streamlit.

Lê o SQLite só via automacao/db.py (nunca SQL direto aqui). Sem FastAPI, sem pandas:
volume pequeno o suficiente para dict/list puro + st.bar_chart (aceita dict nativamente).

Rodar com: streamlit run automacao/dashboard/app.py
"""

import streamlit as st

from automacao import db
from automacao.pipeline import scoring

st.set_page_config(page_title="CV Optimizer — Automação", layout="wide")
db.init_db()

profiles = {p["id"]: p for p in scoring.load_all_profiles()}
profile_id = st.sidebar.selectbox("Perfil", list(profiles.keys()))

st.title(f"Vagas — {profile_id}")

tab_jobs, tab_gap, tab_applications = st.tabs(["Vagas pontuadas", "Análise de gap", "Candidaturas"])

with tab_jobs:
    jobs = db.list_jobs(profile_id=profile_id)
    if not jobs:
        st.info("Nenhuma vaga pontuada ainda para este perfil. Rode o pipeline de discovery primeiro.")
    for job in jobs:
        with st.container(border=True):
            st.markdown(f"**{job['title']}** — {job['company']} · score {job['score']:.2f}")
            st.write(job["url"])

with tab_gap:
    st.caption(
        "Frequência de keywords nas vagas pontuadas deste perfil, cruzada com o cv-base do candidato. "
        "TODO: stack_overlap/gap ficam zerados até cv-base.yaml existir como fonte estruturada."
    )
    gap = db.keyword_gap(profile_id, candidate_keywords=set())
    missing = {row["keyword"]: row["frequency"] for row in gap if row["missing"]}
    if missing:
        st.bar_chart(missing)
    else:
        st.info("Sem dados de gap ainda.")

with tab_applications:
    applications = db.list_applications(profile_id=profile_id)
    if not applications:
        st.info("Nenhuma candidatura registrada ainda.")
    for app in applications:
        st.write(f"{app['company']} — {app['title']} · status: **{app['status']}**")
