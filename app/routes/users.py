from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request, HTTPException
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


@router.get("/users")
def list_users(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", status_code=302)
    if current_user.is_admin:
        pending = db.query(User).filter(User.is_active.is_(False)).all()
        users = db.query(User).filter(User.is_active.is_(True)).all()
    else:
        pending = []
        users = [current_user]
    return templates.TemplateResponse(
        "users.html",
        {
            "request": request,
            "title": "Usuarios",
            "header_title": "Usuarios",
            "users": users,
            "pending": pending,
            "user": current_user,
        },
    )


@router.get("/users/{user_id}/edit")
def edit_user_form(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", status_code=302)
    if not current_user.is_admin and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="No autorizado")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return templates.TemplateResponse(
        "user_form.html",
        {
            "request": request,
            "title": "Editar usuario",
            "header_title": "Editar usuario",
            "u": user,
            "user": current_user,
        },
    )


@router.post("/users/{user_id}/edit")
def edit_user(
    user_id: int,
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", status_code=302)
    if not current_user.is_admin and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="No autorizado")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    existing = (
        db.query(User)
        .filter((User.username == username) | (User.email == email))
        .filter(User.id != user_id)
        .first()
    )
    if existing:
        return templates.TemplateResponse(
            "user_form.html",
            {
                "request": request,
                "title": "Editar usuario",
                "header_title": "Editar usuario",
                "u": {"id": user_id, "username": username, "email": email},
                "user": current_user,
                "error": "Usuario o email existente",
            },
            status_code=400,
        )
    user.username = username
    user.email = email
    if password:
        user.password_hash = hash_password(password)
    db.add(user)
    db.commit()
    return RedirectResponse("/users", status_code=302)


@router.post("/users/{user_id}/delete")
def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", status_code=302)
    if not current_user.is_admin and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="No autorizado")
    user = db.get(User, user_id)
    if user:
        db.delete(user)
        db.commit()
    if current_user.id == user_id:
        request.session.clear()
        return RedirectResponse("/login", status_code=302)
    return RedirectResponse("/users", status_code=302)


@router.post("/users/{user_id}/approve", dependencies=[Depends(require_admin)])
def approve_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user:
        user.is_active = True
        db.add(user)
        db.commit()
    return RedirectResponse("/users", status_code=302)


@router.post("/users/{user_id}/toggle")
def toggle_admin(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if user_id == current_user.id:
        return RedirectResponse("/users", status_code=302)
    user = db.get(User, user_id)
    if user:
        user.is_admin = not user.is_admin
        db.add(user)
        db.commit()
    return RedirectResponse("/users", status_code=302)

