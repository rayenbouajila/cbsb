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
app = FastAPI(title="Auth API - Client/Admin")
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
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "login.html",
        {"request": request}
    )
@app.get("/client-dashboard")
def client_dashboard():
    return FileResponse("frontend/client-dashboard.html")
