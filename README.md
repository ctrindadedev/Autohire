> WORK IN PROGRESS

# CV Optimizer & Job Discovery Automation

ATS-focused resume optimization powered by Claude Code, plus a Python automation that discovers job postings from public feeds/APIs, scores them deterministically against your profile, and emails you when something worth pursuing shows up.

Built with a focus on keeping a human in the loop for anything a platform's ToS restricts (no auto-apply bots), deterministic scoring instead of LLM calls in the background pipeline, and a shared data-access layer instead of a premature API/DB coupling.

![status](https://img.shields.io/badge/status-work%20in%20progress-yellow)
![python](https://img.shields.io/badge/python-3.12-blue?logo=python&logoColor=white)
![no llm in pipeline](https://img.shields.io/badge/background%20pipeline-no%20LLM%20calls-informational)

## 💻 Tech Stack

<div style="display: flex; flex-wrap: wrap; gap: 15px; margin-top: 10px; margin-bottom: 20px;">
  <img align="center" alt="Python" height="50" src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/python/python-original.svg"/>
  <img align="center" alt="SQLite" height="50" src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/sqlite/sqlite-plain.svg"/>
  <img align="center" alt="GitHub Actions" height="50" src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/githubactions/githubactions-plain.svg"/>
  <img align="center" alt="HTML5" height="50" src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/html5/html5-original.svg"/>
  <img align="center" alt="CSS3" height="50" src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/css3/css3-original.svg"/>
  <img align="center" alt="Streamlit" height="50" src="https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white"/>
</div>

## 📖 About the Repository

This repository contains two independent pieces that share the same goal — spending less manual effort per job application without cutting corners that would hurt ATS pass rates or violate a platform's terms of service.

1. **Resume optimization (manual, via Claude Code)** — rules live in [`CLAUDE.md`](./CLAUDE.md). You drop a job description into `vagas/[company].md`, ask Claude Code to optimize, and it generates `output/cv-[company].html` following ATS, metrics, and bullet-point rules.
2. **Job discovery automation (`automacao/`)** — a Python pipeline scheduled via GitHub Actions cron that fetches jobs from RSS/API sources, scores them against a configurable profile, and emails a digest when something crosses the notification threshold. It intentionally does **not** generate a CV or call any LLM — it hands you the raw scored job so you can decide whether to hand it back to step 1.

## Key Features

### 📝 Resume Optimization
- ATS-safe HTML template — no columns/grids/tables that break Workday/Taleo/iCIMS parsers.
- Keyword extraction from the job description, mirrored into Professional Summary and Technical Skills.
- Bullet rewriting with the XYZ formula (strong verb + measurable outcome + business impact), metrics flagged with `[REVISAR MÉTRICA]` instead of invented.
- Layout constrained to a 2-page A4 print via CSS `@media print`.

### 🔎 Job Discovery Automation
- Deterministic keyword-matching score per profile — **no LLM call anywhere in the background pipeline**, so it scales to hundreds of jobs per feed run without a per-token bill.
- Multi-profile config (`automacao/config/profiles/*.yaml`): different people, objectives (internship / full-time / remote-intl) and skill taxonomies share the same pipeline, only weights and sources change.
- Per-source polling cadence (`poll_interval_hours`) instead of one global cron — respects each API's own rate limits.
- Deduplication by normalized company+title key, so the same posting from multiple feeds doesn't double-count.

### 📊 Dashboard & Gap Analysis
- Streamlit dashboard reading straight from SQLite through a single shared data-access module (`db.py`) — no separate API server to run for a two-person, low-volume project.
- Aggregated keyword-gap analysis: which skills show up most often across scored jobs but are missing from your resume — computed with plain SQL `GROUP BY`, no pandas needed at this volume.
- Application tracking table (found → CV generated → submitted → interview → rejected/offer), not just a scored job list.

### 🔐 Scope & Safety
- Notification channel is e-mail, not WhatsApp/LinkedIn automation — avoids account-ban risk from unofficial protocol reimplementations or ToS violations.
- The final "submit application" click is always human, especially on ATS platforms with active anti-bot protection (confirmed 403s on direct fetch during research).

## TO-DO
- [ ] `cv-base.yaml` as the structured source of truth (today `cv-base.html` still requires HTML parsing; blocks real `stack_overlap` scoring).
- [ ] Validate `remoteok.com/api` with an explicit `User-Agent` header in Python (403 on the naive fetch test — inconclusive, not necessarily closed).
- [ ] HTML-parser fallback for BR internship aggregators with no discoverable feed (estagiotrainee.com, jcconcursos.com.br) — highest technical risk in the project.
- [ ] Validate the `data-engineering` role taxonomy with the collaborator who'll use that profile (currently just a placeholder example).
- [ ] Implement a real company-size/funding signal instead of the neutral placeholder in `scoring.py`.
- [ ] Calibrate `notify_threshold` per profile against real scored data (currently a guessed fixed value).

---

## 🛠️ How to run the project locally

### Prerequisites
- Python 3.12+
- Claude Code (for the resume-optimization flow)

### Resume Optimization Setup
1. Add the job description to `vagas/[company].md`.
2. Ask Claude Code: *"Optimize my resume for vagas/[company].md"*.
3. Review `output/cv-[company].html`, resolve any `[REVISAR MÉTRICA]` marker, export to PDF.

### Automation Setup
1. Navigate to the `automacao` folder.
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Create your own profile — the whole `config/profiles/` folder is gitignored (personal e-mail and
   file paths), so there's no example file to copy; create `config/profiles/<your-id>.yaml` from
   scratch with this shape:

   ```yaml
   id: <your-id>
   owner: <your-name>
   cv_base_path: ../cv-base.html
   role_taxonomy: dev-fullstack        # matches a file in config/taxonomies/
   objective: estagio                  # estagio | clt | remoto-intl
   language: pt                        # pt | en
   sources: [weworkremotely-programming, remotive-api]   # ids from config/sources.yaml
   scoring_weights:
     remote_modality: 0.4
     stack_overlap: 0.5
     company_size_signal: 0.1
   notify_threshold: 0.6
   notify_channel: "email:you@example.com"
   ```

4. Configure SMTP credentials:

   ```bash
   cp .env.example .env   # fill in SMTP_USER / SMTP_PASSWORD
   ```

5. Run the pipeline once (discovery → score → email digest):

   ```bash
   python -m pipeline.run
   ```

6. Launch the dashboard:

   ```bash
   streamlit run dashboard/app.py
   ```

In production, `.github/workflows/discovery.yml` runs the same pipeline on a cron schedule and commits the updated SQLite file back to the repo — configure `SMTP_USER`/`SMTP_PASSWORD` as repository secrets before enabling it.

## 🔒 Privacy — what stays local vs. what's public

This repo is public, so personal data is gitignored on purpose — only code and templates are tracked.
If you're a collaborator setting this up, follow the same pattern:

| Stays local (gitignored) | Tracked in git |
|---|---|
| `cv-base.html`, your resume PDF | `CLAUDE.md` (the HTML template lives inside it) |
| `output/*.html` (generated CVs) | `output/.gitkeep` (folder structure only) |
| `vagas/*.md`, `prep/*.md` (your job research/notes) | `vagas/.gitkeep`, `prep/.gitkeep` |
| `automacao/config/profiles/*` — every profile file (your real e-mail, paths) | `automacao/config/profiles/.gitkeep` (folder structure only — see "Automation Setup" for the format) |
| `automacao/.env` (SMTP credentials) | `automacao/.env.example` |

`automacao/data/jobs.db` **is** tracked — it's how the SQLite file survives across ephemeral GitHub
Actions runs, but it also means job data + application notes for whoever runs this pipeline live in the
public repo. If that's a concern for your use case, keep the automation running against a private
fork/branch instead of this public one, or swap SQLite for a private hosted DB.
