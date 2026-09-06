"""Notificação por e-mail (decidido: e-mail, não WhatsApp).

O e-mail entrega a vaga BRUTA pontuada + keywords de gap por matching — não um CV pronto.
A automação não chama LLM; detalhamento da vaga e geração de CV continuam manuais,
feitos no Claude Code a partir deste e-mail.
"""

import os
import smtplib
from email.message import EmailMessage

from automacao import db

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")


def _render_digest(profile_id: str, jobs: list[dict]) -> str:
    lines = [f"Vagas novas para o perfil {profile_id}:\n"]
    for job in jobs:
        lines.append(
            f"- {job['title']} @ {job['company']} (score {job['score']:.2f})\n"
            f"  {job['url']}\n"
        )
    lines.append(
        "\nPróximo passo: abra o Claude Code e peça para pesquisar/detalhar a vaga de interesse "
        "e gerar o CV (Fluxo B do CLAUDE.md) — este e-mail não gera o CV automaticamente."
    )
    return "\n".join(lines)


def send_digest(profile: dict, jobs: list[dict]) -> None:
    if not jobs:
        return
    if not (SMTP_USER and SMTP_PASSWORD):
        raise RuntimeError(
            "SMTP_USER/SMTP_PASSWORD não configurados (ver .env.example). "
            "Sem isso o pipeline não consegue enviar notificação."
        )

    to_address = profile["notify_channel"].removeprefix("email:").strip()
    message = EmailMessage()
    message["Subject"] = f"[CV Optimizer] {len(jobs)} vaga(s) nova(s) — {profile['id']}"
    message["From"] = SMTP_USER
    message["To"] = to_address
    message.set_content(_render_digest(profile["id"], jobs))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(message)

    for job in jobs:
        db.mark_notified(job["id"], profile["id"])
