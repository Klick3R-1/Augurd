import logging
from typing import Optional

import database
from worker import ServerWorker

logger = logging.getLogger(__name__)

# server_id → ServerWorker
_workers: dict[int, ServerWorker] = {}


async def _build_worker(server_id: int) -> Optional[ServerWorker]:
    server = await database.get_server(server_id)
    if not server:
        return None
    log_sources = await database.get_log_sources(server_id)
    settings = await database.get_settings()
    return ServerWorker(server=server, log_sources=log_sources, settings=settings)


async def start_worker(server_id: int) -> bool:
    worker = _workers.get(server_id)

    if worker and worker.is_running():
        return True

    # Rebuild worker so it picks up the latest config/settings
    worker = await _build_worker(server_id)
    if not worker:
        logger.error(f"Server {server_id} not found")
        return False

    _workers[server_id] = worker
    await worker.start()
    logger.info(f"Started worker for server {server_id}")
    return True


async def stop_worker(server_id: int):
    worker = _workers.get(server_id)
    if worker:
        await worker.stop()
        logger.info(f"Stopped worker for server {server_id}")


async def stop_all():
    for server_id, worker in list(_workers.items()):
        if worker.is_running():
            await worker.stop()
    _workers.clear()


def get_worker(server_id: int) -> Optional[ServerWorker]:
    return _workers.get(server_id)


def get_status(server_id: int) -> dict:
    worker = _workers.get(server_id)
    if not worker:
        return {"status": "stopped", "error": None, "last_alert": None, "alert_count": 0}
    return {
        "status": worker.status,
        "error": worker.error,
        "last_alert": worker.last_alert.isoformat() if worker.last_alert else None,
        "alert_count": worker.alert_count,
    }


def all_statuses() -> dict[int, dict]:
    return {sid: get_status(sid) for sid in _workers}
