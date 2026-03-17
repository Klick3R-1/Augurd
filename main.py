import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import database
import ollama_client
import worker_manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init_db()
    yield
    await worker_manager.stop_all()


app = FastAPI(title="localmon", lifespan=lifespan)
templates = Jinja2Templates(directory="templates")


def redirect(path: str):
    return RedirectResponse(url=path, status_code=303)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    servers = await database.get_all_servers()
    alerts = await database.get_recent_alerts(limit=30)
    statuses = worker_manager.all_statuses()

    # Attach worker status + log source count to each server
    for s in servers:
        sid = s["id"]
        sources = await database.get_log_sources(sid)
        s["source_count"] = len(sources)
        s["active_source_count"] = sum(1 for src in sources if src["enabled"])
        s["worker"] = statuses.get(sid, {"status": "stopped", "error": None, "last_alert": None, "alert_count": 0})

    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "servers": servers, "alerts": alerts},
    )


# ---------------------------------------------------------------------------
# Server CRUD
# ---------------------------------------------------------------------------

@app.get("/servers/new", response_class=HTMLResponse)
async def server_new(request: Request):
    return templates.TemplateResponse(
        "server_form.html",
        {"request": request, "server": None, "log_sources": [], "errors": []},
    )


@app.post("/servers")
async def server_create(
    name: str = Form(...),
    host: str = Form(...),
    port: int = Form(22),
    username: str = Form(...),
    ssh_key_path: str = Form(""),
    ssh_password: str = Form(""),
    force_password_auth: str = Form(""),
):
    server_id = await database.create_server(
        name=name,
        host=host,
        port=port,
        username=username,
        ssh_key_path=ssh_key_path.strip() or None,
        ssh_password=ssh_password.strip() or None,
        force_password_auth=bool(force_password_auth),
    )
    return redirect(f"/servers/{server_id}")


@app.get("/servers/{server_id}", response_class=HTMLResponse)
async def server_detail(request: Request, server_id: int):
    server = await database.get_server(server_id)
    if not server:
        return redirect("/")
    log_sources = await database.get_log_sources(server_id)
    alerts = await database.get_server_alerts(server_id, limit=20)
    status = worker_manager.get_status(server_id)
    return templates.TemplateResponse(
        "server_form.html",
        {
            "request": request,
            "server": server,
            "log_sources": log_sources,
            "alerts": alerts,
            "worker": status,
            "errors": [],
        },
    )


@app.post("/servers/{server_id}/edit")
async def server_update(
    server_id: int,
    name: str = Form(...),
    host: str = Form(...),
    port: int = Form(22),
    username: str = Form(...),
    ssh_key_path: str = Form(""),
    ssh_password: str = Form(""),
    force_password_auth: str = Form(""),
):
    await database.update_server(
        server_id=server_id,
        name=name,
        host=host,
        port=port,
        username=username,
        ssh_key_path=ssh_key_path.strip() or None,
        ssh_password=ssh_password.strip() or None,
        force_password_auth=bool(force_password_auth),
    )
    # Restart worker if running so it picks up new connection details
    if worker_manager.get_status(server_id)["status"] == "running":
        await worker_manager.stop_worker(server_id)
        await worker_manager.start_worker(server_id)
    return redirect(f"/servers/{server_id}")


@app.post("/servers/{server_id}/delete")
async def server_delete(server_id: int):
    await worker_manager.stop_worker(server_id)
    await database.delete_server(server_id)
    return redirect("/")


# ---------------------------------------------------------------------------
# Log sources
# ---------------------------------------------------------------------------

@app.post("/servers/{server_id}/log-sources")
async def log_source_add(
    server_id: int,
    source_type: str = Form(...),
    source: str = Form(...),
):
    await database.add_log_source(
        server_id=server_id,
        source_type=source_type,
        source=source.strip(),
    )
    # Restart worker to pick up new source
    if worker_manager.get_status(server_id)["status"] == "running":
        await worker_manager.stop_worker(server_id)
        await worker_manager.start_worker(server_id)
    return redirect(f"/servers/{server_id}")


@app.post("/servers/{server_id}/log-sources/{source_id}/delete")
async def log_source_delete(server_id: int, source_id: int):
    await database.delete_log_source(source_id)
    if worker_manager.get_status(server_id)["status"] == "running":
        await worker_manager.stop_worker(server_id)
        await worker_manager.start_worker(server_id)
    return redirect(f"/servers/{server_id}")


# ---------------------------------------------------------------------------
# Worker control
# ---------------------------------------------------------------------------

@app.post("/workers/{server_id}/start")
async def worker_start(server_id: int):
    await worker_manager.start_worker(server_id)
    return redirect(f"/servers/{server_id}")


@app.post("/workers/{server_id}/stop")
async def worker_stop(server_id: int):
    await worker_manager.stop_worker(server_id)
    return redirect(f"/servers/{server_id}")


@app.get("/api/workers/{server_id}/status")
async def worker_status_api(server_id: int, request: Request):
    status = worker_manager.get_status(server_id)
    return templates.TemplateResponse(
        "_status_badge.html",
        {"request": request, "worker": status, "server_id": server_id},
    )


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    settings = await database.get_settings()
    ollama_url = settings.get("ollama_url", "http://localhost:11434")
    models = await ollama_client.get_models(ollama_url)
    return templates.TemplateResponse(
        "settings.html",
        {"request": request, "settings": settings, "models": models},
    )


@app.post("/settings")
async def settings_save(
    discord_webhook_url: str = Form(""),
    ollama_url: str = Form("http://localhost:11434"),
    ollama_model: str = Form(""),
    buffer_lines: str = Form("20"),
    buffer_seconds: str = Form("30"),
    alert_cooldown_minutes: str = Form("5"),
):
    await database.update_settings({
        "discord_webhook_url": discord_webhook_url.strip(),
        "ollama_url": ollama_url.strip(),
        "ollama_model": ollama_model.strip(),
        "buffer_lines": buffer_lines.strip(),
        "buffer_seconds": buffer_seconds.strip(),
        "alert_cooldown_minutes": alert_cooldown_minutes.strip(),
    })
    return redirect("/settings")
