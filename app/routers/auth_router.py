from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, auth_utils
from ..database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=schemas.UserOut)
def register(payload: schemas.RegisterRequest, db: Session = Depends(get_db)):
    """Le client demande un compte : statut 'pending' jusqu'a validation admin."""
    existing = db.query(models.User).filter(models.User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Cet email est deja utilise")

    user = models.User(
    email=payload.email,
    full_name=payload.full_name,
    company_name=payload.company_name,
    password_hash=auth_utils.hash_password(payload.password),
    role=models.RoleEnum.client,
    status=models.StatusEnum.pending,
)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/activate")
def activate(payload: schemas.ActivateRequest, db: Session = Depends(get_db)):
    """Le client definit son mot de passe apres validation admin."""
    user_id = auth_utils.decode_activation_token(payload.token)
    user = db.query(models.User).filter(models.User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if user.status != models.StatusEnum.active:
        raise HTTPException(status_code=400, detail="Compte non valide par l'administrateur")

    user.password_hash = auth_utils.hash_password(payload.password)
    db.commit()
    return {"detail": "Compte active. Vous pouvez vous connecter."}


@router.post("/login", response_model=schemas.Token)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email).first()

    if not user or not user.password_hash:
        raise HTTPException(status_code=400, detail="Email ou mot de passe incorrect")
    if not auth_utils.verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Email ou mot de passe incorrect")
    if user.status == models.StatusEnum.pending:
        raise HTTPException(status_code=403, detail="Compte en attente de validation")
    if user.status == models.StatusEnum.rejected:
        raise HTTPException(status_code=403, detail="Demande de compte refusee")

    token = auth_utils.create_access_token({"sub": str(user.id)})
    return schemas.Token(access_token=token, role=user.role, status=user.status)


@router.get("/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(auth_utils.get_current_user)):
    return current_user
