from datetime import datetime, timedelta, timezone
import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .. import models, schemas, auth_utils
from ..database import get_db
from ..services.email_service import send_verification_email, EmailSendingError

router = APIRouter(prefix="/auth", tags=["auth"])

otp_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

CODE_EXPIRATION_MINUTES = 10
MAX_VERIFICATION_ATTEMPTS = 5
RESEND_COOLDOWN_SECONDS = 60


def _generate_otp_code() -> str:
    """Code à 6 chiffres cryptographiquement sûr (peut commencer par 0)."""
    return f"{secrets.randbelow(1_000_000):06d}"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _safe_send_verification_email(email: str, full_name: str, code: str) -> None:
    """Utilisé dans BackgroundTasks : on logue l'erreur SMTP sans jamais
    faire planter la tâche de fond (elle n'a pas de retour HTTP)."""
    try:
        send_verification_email(email, full_name, code)
    except EmailSendingError as exc:
        import logging
        logging.getLogger("auth").error(
            "Échec d'envoi de l'email de vérification à %s : %s", email, exc
        )


@router.post("/register", response_model=schemas.UserOut)
def register(
    payload: schemas.RegisterRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Le client demande un compte : statut 'pending' jusqu'a validation admin,
    et email_verified=False jusqu'a saisie du code OTP reçu par email."""
    existing = db.query(models.User).filter(models.User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Cet email est deja utilise")
    existing = db.query(models.User).filter(models.User.matricule_fiscal == payload.matricule_fiscal).first()
    if existing:
        raise HTTPException(status_code=400, detail="Ce matricule fiscal est deja utilise")

    code = _generate_otp_code()

    user = models.User(
        email=payload.email,
        matricule_fiscal=payload.matricule_fiscal,
        full_name=payload.full_name,
        company_name=payload.company_name,
        password_hash=auth_utils.hash_password(payload.password),
        role=models.RoleEnum.client,
        status=models.StatusEnum.pending,
        email_verified=False,
        verification_code_hash=otp_context.hash(code),
        verification_code_expires_at=_now_utc() + timedelta(minutes=CODE_EXPIRATION_MINUTES),
        verification_attempts=0,
        last_verification_sent_at=_now_utc(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    background_tasks.add_task(_safe_send_verification_email, user.email, user.full_name, code)

    return user


@router.post("/verify-email", response_model=schemas.VerificationMessageResponse)
def verify_email(payload: schemas.EmailVerificationRequest, db: Session = Depends(get_db)):
    """Vérifie le code OTP reçu par email juste après l'inscription."""
    user = db.query(models.User).filter(models.User.email == payload.email).first()

    if not user:
        raise HTTPException(status_code=400, detail="Code invalide ou expire")

    if user.email_verified:
        return {"message": "Cette adresse email est deja verifiee."}

    if not user.verification_code_hash or not user.verification_code_expires_at:
        raise HTTPException(status_code=400, detail="Aucun code en attente. Demandez un nouveau code.")

    if user.verification_attempts >= MAX_VERIFICATION_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Nombre maximal de tentatives atteint. Demandez un nouveau code.",
        )

    if _now_utc() > user.verification_code_expires_at:
        raise HTTPException(status_code=400, detail="Ce code a expire. Demandez un nouveau code.")

    if not otp_context.verify(payload.code, user.verification_code_hash):
        user.verification_attempts += 1
        db.commit()
        remaining = MAX_VERIFICATION_ATTEMPTS - user.verification_attempts
        raise HTTPException(
            status_code=400,
            detail=f"Code incorrect. Tentatives restantes : {max(remaining, 0)}.",
        )

    user.email_verified = True
    user.verification_code_hash = None
    user.verification_code_expires_at = None
    user.verification_attempts = 0
    db.commit()

    return {"message": "Email verifie avec succes. Votre demande est en attente de validation."}


@router.post("/resend-verification-code", response_model=schemas.VerificationMessageResponse)
def resend_verification_code(
    payload: schemas.ResendVerificationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Renvoie un nouveau code OTP, avec limitation anti-abus."""
    user = db.query(models.User).filter(models.User.email == payload.email).first()

    generic_message = {"message": "Si un compte existe avec cet email, un nouveau code a ete envoye."}

    if not user:
        # Reponse generique : on ne confirme pas l'existence du compte
        return generic_message

    if user.email_verified:
        return {"message": "Cette adresse email est deja verifiee."}

    if user.last_verification_sent_at:
        elapsed = (_now_utc() - user.last_verification_sent_at).total_seconds()
        if elapsed < RESEND_COOLDOWN_SECONDS:
            wait = int(RESEND_COOLDOWN_SECONDS - elapsed)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Veuillez patienter {wait} secondes avant de redemander un code.",
            )

    code = _generate_otp_code()
    user.verification_code_hash = otp_context.hash(code)
    user.verification_code_expires_at = _now_utc() + timedelta(minutes=CODE_EXPIRATION_MINUTES)
    user.verification_attempts = 0
    user.last_verification_sent_at = _now_utc()
    db.commit()

    background_tasks.add_task(_safe_send_verification_email, user.email, user.full_name, code)

    return generic_message


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
    user = db.query(models.User).filter(models.User.matricule_fiscal == payload.matricule_fiscal).first()

    if not user or not user.password_hash:
        raise HTTPException(status_code=400, detail="Matricule fiscal ou mot de passe incorrect")
    if not auth_utils.verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Matricule fiscal ou mot de passe incorrect")
    if not user.email_verified:
        raise HTTPException(status_code=403, detail="Veuillez d'abord verifier votre adresse email")
    if user.status == models.StatusEnum.pending:
        raise HTTPException(status_code=403, detail="Compte en attente de validation")
    if user.status == models.StatusEnum.rejected:
        raise HTTPException(status_code=403, detail="Demande de compte refusee")

    token = auth_utils.create_access_token({"sub": str(user.id)})
    return schemas.Token(access_token=token, role=user.role, status=user.status)


@router.get("/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(auth_utils.get_current_user)):
    return current_user