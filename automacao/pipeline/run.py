"""Orquestrador: discovery -> score -> notificação. Disparado pelo cron do GitHub Actions
(.github/workflows/discovery.yml) ou manualmente com `python -m automacao.pipeline.run`.
"""

from automacao import db
from automacao.pipeline import discovery, notify, scoring


def main() -> None:
    db.init_db()

    new_job_ids = discovery.run_discovery()
    scoring.score_all_pending(new_job_ids)

    for profile in scoring.load_all_profiles():
        pending = db.list_pending_notifications(profile["id"], profile["notify_threshold"])
        notify.send_digest(profile, pending)


if __name__ == "__main__":
    main()
