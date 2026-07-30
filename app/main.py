from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from . import models, auth_utils
from .database import engine, SessionLocal
from .routers import auth_router, admin_router,contact,invoices_router,deliverables_router,export_router,fiscal_router, payments_router,messages_router,fiscal_router
from fastapi import Request
from fastapi.responses import HTMLResponse





models.Base.metadata.create_all(bind=engine)
app = FastAPI(title="Cabinet Ben Said Belgacem")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5500", "http://127.0.0.1:5500"],  # a restreindre en production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="frontend")
app.include_router(fiscal_router.router)
app.include_router(messages_router.router)
app.include_router(fiscal_router.router)
app.include_router(payments_router.router)
app.include_router(export_router.router)
app.include_router(deliverables_router.router)
app.include_router(auth_router.router)
app.include_router(admin_router.router)
app.include_router(contact.router)
app.include_router(invoices_router.router)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )


@app.get("/login")
def login_page():
    return FileResponse("frontend/login.html")


@app.get("/signup")
def signup_page():
    return FileResponse("frontend/signup.html")

from fastapi.responses import FileResponse


@app.get("/admin-dashboard")
def admin_dashboard():
    return FileResponse("frontend/admin-dashboard.html")

@app.get("/client-dashboard")
def client_dashboard():
    return FileResponse("frontend/client-dashboard.html")
@app.on_event("startup")
def create_default_admin():
    db = SessionLocal()
    try:
        exists = db.query(models.User).filter(models.User.role == models.RoleEnum.admin).first()
        if not exists:
            admin = models.User(
                email="admin@comptaflow.com",
                password_hash=auth_utils.hash_password("rayen123"),
                role=models.RoleEnum.admin,
                status=models.StatusEnum.active,
                full_name="Administrateur",
            )
            db.add(admin)
            db.commit()
            print("Compte admin cree : admin@comptaflow.com / rayen123")
    finally:
        db.close()
