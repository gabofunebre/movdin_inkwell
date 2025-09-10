from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from sqlalchemy.orm import Session

from config.db import get_db, init_db
from config.constants import CURRENCY_SYMBOLS
from models import Account, Invoice
from routes.accounts import router as accounts_router
from routes.health import router as health_router
from routes.transactions import router as transactions_router
from routes.frequents import router as frequents_router
from routes.invoices import router as invoices_router

app = FastAPI(title="Movimientos")

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


@app.on_event("startup")
def on_startup() -> None:
    init_db()

app.include_router(health_router)
app.include_router(accounts_router)
app.include_router(transactions_router)
app.include_router(frequents_router)
app.include_router(invoices_router)

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


@app.get("/billing.html", response_class=HTMLResponse)
async def billing(request: Request, db: Session = Depends(get_db)):
    acc = db.query(Account).filter(Account.is_billing.is_(True)).first()
    if acc:
        title = f"Facturación - {acc.name}"
        header_title = (
            f"Facturación - <span style=\"color:{acc.color}\">{acc.name}</span>"
        )
    else:
        title = "Facturación"
        header_title = "Facturación"
    return templates.TemplateResponse(
        "billing.html",
        {"request": request, "title": title, "header_title": header_title},
    )


@app.get("/invoice/{invoice_id}", response_class=HTMLResponse)
async def invoice_detail(
    request: Request, invoice_id: int, db: Session = Depends(get_db)
):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    acc = db.get(Account, inv.account_id)
    symbol = CURRENCY_SYMBOLS.get(acc.currency) if acc else ""
    total = inv.amount + inv.iva_amount
    return templates.TemplateResponse(
        "invoice_detail.html",
        {
            "request": request,
            "title": "Factura",
            "header_title": "Detalle de factura",
            "invoice": inv,
            "account": acc,
            "symbol": symbol,
            "total": total,
        },
    )
