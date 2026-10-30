from celery import Celery

from app.core.config import get_settings

settings = get_settings()
celery_app = Celery("stock_research", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(task_track_started=True, task_serializer="json", result_serializer="json", accept_content=["json"])


@celery_app.task(name="stock_research.run_research")
def run_research_task(research_id: str) -> None:
    from app.services.research import run_research

    run_research(research_id)
