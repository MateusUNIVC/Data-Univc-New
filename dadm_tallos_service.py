from __future__ import annotations

import logging
from datetime import datetime, timezone

from database import SessionLocal
from models import DADMTallosSyncRun, Directorate
from security import DirectorateScope, UserContext
from dadm_tallos_client import DADMTallosClient
from dadm_tallos_normalization import normalize_report
from dadm_tallos_repository import DADMTallosRepository

LOGGER = logging.getLogger("univc.dadm.tallos.sync")


def _scope_for_run(db, run: DADMTallosSyncRun) -> DirectorateScope:
    directorate = db.get(Directorate, run.directorate_id)
    if not directorate:
        raise RuntimeError("Diretoria da sincronização não existe mais.")
    user = UserContext(
        user_id="dadm-tallos-sync",
        email=run.requested_by or "dadm-tallos-sync@univc.local",
        full_name="Sincronização TALLOS",
        role="admin",
        directorate_id=directorate.id,
        directorate_code=directorate.code,
        directorate_name=directorate.name,
    )
    return DirectorateScope(
        user=user,
        directorate_id=directorate.id,
        directorate_code=directorate.code,
        directorate_name=directorate.name,
        can_write=True,
        is_home=True,
    )


def execute_sync_run(run_id: int) -> None:
    """Executa uma sincronização persistida, com commit página a página.

    O processo é idempotente por ``source_id`` TALLOS. Reexecutar o mesmo mês
    atualiza avaliações/fechamentos tardios sem duplicar atendimentos.
    """
    db = SessionLocal()
    try:
        run = db.get(DADMTallosSyncRun, run_id)
        if not run:
            LOGGER.error("Sync TALLOS %s não encontrada", run_id)
            return
        scope = _scope_for_run(db, run)
        repo = DADMTallosRepository(db, scope)
        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        run.error_message = None
        db.commit()

        client = DADMTallosClient()

        # Pré-planeje todos os blocos antes de persistir a primeira página. Antes,
        # ``total_expected`` crescia conforme novos blocos de 90 dias eram
        # descobertos e a porcentagem podia retroceder (ex.: 71% -> 67%).
        # Agora o denominador fica estável durante toda a fase determinada.
        plan = client.plan_report_pages(run.start_date, run.end_date)
        run = db.get(DADMTallosSyncRun, run_id)
        run.total_expected = int(plan.total_expected)
        db.commit()

        for first_page in plan.first_pages:
            page_number = max(1, int(first_page.page or 1))
            while page_number <= first_page.pages:
                page = first_page if page_number == first_page.page else client.fetch_report_page(
                    first_page.start_date, first_page.end_date, page_number
                )
                normalized: list[dict] = []
                failed = 0
                for row in page.docs:
                    try:
                        normalized.append(normalize_report(row, fallback_date=page.start_date))
                    except Exception:
                        LOGGER.exception("Falha ao normalizar um relatório TALLOS na sync %s", run_id)
                        failed += 1
                result = repo.upsert_batch(normalized, sync_run_id=run.id)
                run = db.get(DADMTallosSyncRun, run_id)
                run.pages_processed += 1
                run.records_received += len(page.docs)
                run.records_inserted += result["inserted"]
                run.records_updated += result["updated"]
                run.records_unchanged += result["unchanged"]
                run.records_failed += failed
                db.commit()
                if not page.docs or page.page >= page.pages:
                    break
                page_number = page.page + 1

        run = db.get(DADMTallosSyncRun, run_id)
        # If the source changed while the job was running, preserve truthful history
        # without ever changing the denominator during the active progress phase.
        run.total_expected = max(int(run.total_expected or 0), int(run.records_received or 0))
        run.status = "completed"
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as exc:
        LOGGER.exception("Falha na sincronização TALLOS %s", run_id)
        db.rollback()
        run = db.get(DADMTallosSyncRun, run_id)
        if run:
            run.status = "failed"
            run.error_message = str(exc)[:1000]
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()
