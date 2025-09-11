from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates

from config.db import get_db
from models import User
from auth import hash_password, get_current_user, require_admin


templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")

router = APIRouter()


@router.get("/login")
def login_form(request: Request):
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "title": "Ingresar", "header_title": "Ingresar", "user": None},
    )


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == username).first()
    if not user or user.password_hash != hash_password(password):
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "title": "Ingresar",
                "header_title": "Ingresar",
                "error": "Credenciales inválidas",
                "user": None,
            },
            status_code=400,
        )
    if not user.is_active:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "title": "Ingresar",
                "header_title": "Ingresar",
                "error": "Cuenta pendiente de aprobación",
                "user": None,
            },
            status_code=400,
        )
    request.session["user_id"] = user.id
    return RedirectResponse("/", status_code=302)


@router.get("/register")
def register_form(request: Request):
    return templates.TemplateResponse(
        "register.html",
        {"request": request, "title": "Registro", "header_title": "Registro", "user": None},
    )


@router.post("/register")
def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    if db.query(User).filter((User.username == username) | (User.email == email)).first():
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "title": "Registro",
                "header_title": "Registro",
                "error": "Usuario o email existente",
                "user": None,
            },
            status_code=400,
        )
    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
    )
    db.add(user)
    db.commit()
    return templates.TemplateResponse(
        "register.html",
        {
            "request": request,
            "title": "Registro",
            "header_title": "Registro",
            "message": "Registro exitoso. Un administrador debe aprobar su solicitud.",
            "user": None,
        },
    )


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


@router.get("/users", dependencies=[Depends(require_admin)])
def list_users(request: Request, db: Session = Depends(get_db)):
    pending = db.query(User).filter(User.is_active.is_(False)).all()
    users = db.query(User).filter(User.is_active.is_(True)).all()
    return templates.TemplateResponse(
        "users.html",
        {
            "request": request,
            "title": "Usuarios",
            "header_title": "Usuarios",
            "users": users,
            "pending": pending,
        },
    )


@router.post("/users/{user_id}/delete", dependencies=[Depends(require_admin)])
def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user:
        db.delete(user)
        db.commit()
    return RedirectResponse("/users", status_code=302)


@router.post("/users/{user_id}/approve", dependencies=[Depends(require_admin)])
def approve_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user:
        user.is_active = True
        db.add(user)
        db.commit()
    return RedirectResponse("/users", status_code=302)


@router.post("/users/{user_id}/toggle", dependencies=[Depends(require_admin)])
def toggle_admin(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user:
        user.is_admin = not user.is_admin
        db.add(user)
        db.commit()
    return RedirectResponse("/users", status_code=302)

