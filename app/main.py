from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from config.db import init_db
from routes.accounts import router as accounts_router
from routes.health import router as health_router
from routes.transactions import router as transactions_router
from routes.frequents import router as frequents_router

app = FastAPI(title="Movimientos")

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


@app.on_event("startup")
def on_startup() -> None:
    init_db()

app.include_router(health_router)
app.include_router(accounts_router)
app.include_router(transactions_router)
app.include_router(frequents_router)

app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).parent / "static"),
    name="static",
)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "title": "Movimientos",
            "header_title": "Movimientos de dinero",
        },
    )


@app.get("/config.html", response_class=HTMLResponse)
async def config(request: Request):
    return templates.TemplateResponse(
        "config.html",
        {"request": request, "title": "Configuración", "header_title": "Configuración"},
    )


@app.get("/totals.html", response_class=HTMLResponse)
async def totals(request: Request):
    return templates.TemplateResponse(
        "totals.html",
        {"request": request, "title": "Totales", "header_title": "Totales"},
    )
