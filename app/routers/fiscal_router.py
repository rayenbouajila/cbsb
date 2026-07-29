"""
fiscal_router.py

Module Situation Fiscale - gestion MANUELLE par le comptable (pas de calcul
automatique a partir des factures). A la creation d'une situation fiscale
pour un client + une annee, on genere automatiquement le squelette complet
(lignes mensuelles, annuelles, acomptes) selon le calendrier fiscal tunisien
et le type de contribuable ; le comptable remplit ensuite dates de depot/
paiement, montants, statuts et observations au fil de l'annee.
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas, auth_utils
from ..database import get_db

router = APIRouter(tags=["fiscal"])


# ---------- Generation automatique du squelette (calendrier fiscal) ----------

def _generate_monthly_declarations(fiscal_situation: models.FiscalSituation, year: int, client_type: models.ClientTypeEnum):
    declarations = []
    for month in range(1, 13):
        if client_type == models.ClientTypeEnum.personne_physique:
            declarations.append(models.MonthlyFiscalDeclaration(
                fiscal_situation_id=fiscal_situation.id,
                month=month,
                declaration_type="declaration_mensuelle",
                due_date=date(year, month, 15),
            ))
        else:  # personne_morale : deux echeances distinctes par mois
            declarations.append(models.MonthlyFiscalDeclaration(
                fiscal_situation_id=fiscal_situation.id,
                month=month,
                declaration_type="teledeclaration",
                due_date=date(year, month, 20),
            ))
            declarations.append(models.MonthlyFiscalDeclaration(
                fiscal_situation_id=fiscal_situation.id,
                month=month,
                declaration_type="paiement_recette",
                due_date=date(year, month, 28),
            ))
    return declarations


def _generate_annual_declarations(fiscal_situation: models.FiscalSituation, year: int, client_type: models.ClientTypeEnum):
    declarations = []
    if client_type == models.ClientTypeEnum.personne_physique:
        declarations.append(models.AnnualFiscalDeclaration(
            fiscal_situation_id=fiscal_situation.id,
            declaration_type="activite_commerciale",
            due_date=date(year, 4, 25),
        ))
        declarations.append(models.AnnualFiscalDeclaration(
            fiscal_situation_id=fiscal_situation.id,
            declaration_type="autre_activite",
            due_date=date(year, 5, 25),
        ))
    else:
        declarations.append(models.AnnualFiscalDeclaration(
            fiscal_situation_id=fiscal_situation.id,
            declaration_type="declaration_annuelle",
            due_date=date(year, 3, 25),
        ))

    # Declaration d'impot : commune aux deux types de contribuables
    declarations.append(models.AnnualFiscalDeclaration(
        fiscal_situation_id=fiscal_situation.id,
        declaration_type="declaration_impot",
        due_date=date(year, 4, 30),
    ))
    return declarations


def _generate_provisional_payments(fiscal_situation: models.FiscalSituation, year: int):
    schedule = [(1, 6, 25), (2, 9, 25), (3, 12, 25)]  # (numero, mois, jour)
    return [
        models.ProvisionalPayment(
            fiscal_situation_id=fiscal_situation.id,
            installment_number=num,
            due_date=date(year, month, day),
        )
        for num, month, day in schedule
    ]


def _get_fiscal_situation_or_404(db: Session, client_id: int, year: int) -> models.FiscalSituation:
    situation = (
        db.query(models.FiscalSituation)
        .options(
            joinedload(models.FiscalSituation.monthly_declarations),
            joinedload(models.FiscalSituation.annual_declarations),
            joinedload(models.FiscalSituation.provisional_payments),
        )
        .filter(models.FiscalSituation.client_id == client_id, models.FiscalSituation.year == year)
        .first()
    )
    if not situation:
        raise HTTPException(status_code=404, detail="Aucune situation fiscale pour cette annee. Creez-la d'abord.")
    return situation


# ---------- Admin ----------

@router.get("/admin/clients/{client_id}/fiscal-status", response_model=schemas.FiscalSituationOut)
def admin_get_fiscal_status(
    client_id: int,
    year: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth_utils.require_admin),
):
    year = year or date.today().year
    client = db.query(models.User).filter(
        models.User.id == client_id, models.User.role == models.RoleEnum.client,
    ).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client introuvable")

    return _get_fiscal_situation_or_404(db, client_id, year)


@router.post("/admin/clients/{client_id}/fiscal-status", response_model=schemas.FiscalSituationOut)
def admin_create_fiscal_status(
    client_id: int,
    payload: schemas.FiscalSituationCreate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth_utils.require_admin),
):
    client = db.query(models.User).filter(
        models.User.id == client_id, models.User.role == models.RoleEnum.client,
    ).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client introuvable")

    existing = db.query(models.FiscalSituation).filter(
        models.FiscalSituation.client_id == client_id,
        models.FiscalSituation.year == payload.year,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Une situation fiscale existe deja pour ce client et cette annee.")

    situation = models.FiscalSituation(client_id=client_id, year=payload.year, client_type=payload.client_type)
    db.add(situation)
    db.flush()  # situation.id disponible pour les lignes enfants

    db.add_all(_generate_monthly_declarations(situation, payload.year, payload.client_type))
    db.add_all(_generate_annual_declarations(situation, payload.year, payload.client_type))
    db.add_all(_generate_provisional_payments(situation, payload.year))

    db.commit()
    return _get_fiscal_situation_or_404(db, client_id, payload.year)


@router.put("/admin/fiscal-status/{item_id}")
def admin_update_fiscal_line(
    item_id: int,
    payload: schemas.FiscalLineUpdate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth_utils.require_admin),
):
    """Met a jour UNE ligne (mensuelle, annuelle ou acompte). `entity_type`
    dans le payload determine la table cible pour `item_id`."""
    model_map = {
        "monthly": models.MonthlyFiscalDeclaration,
        "annual": models.AnnualFiscalDeclaration,
        "provisional": models.ProvisionalPayment,
    }
    model_cls = model_map.get(payload.entity_type)
    if not model_cls:
        raise HTTPException(status_code=400, detail="entity_type invalide (monthly | annual | provisional)")

    item = db.query(model_cls).filter(model_cls.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Ligne introuvable")

    if payload.status is not None:
        item.status = payload.status
    if payload.notes is not None:
        item.notes = payload.notes

    if payload.entity_type == "monthly":
        if payload.submission_date is not None:
            item.submission_date = payload.submission_date
        if payload.payment_date is not None:
            item.payment_date = payload.payment_date
    elif payload.entity_type == "annual":
        if payload.submission_date is not None:
            item.submission_date = payload.submission_date
        if payload.amount is not None:
            item.amount = payload.amount
    elif payload.entity_type == "provisional":
        if payload.payment_date is not None:
            item.payment_date = payload.payment_date
        if payload.amount is not None:
            item.amount = payload.amount

    db.commit()
    db.refresh(item)
    return {"status": "updated", "id": item.id}


@router.delete("/admin/clients/{client_id}/fiscal-status/{year}")
def admin_delete_fiscal_status(
    client_id: int,
    year: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth_utils.require_admin),
):
    situation = db.query(models.FiscalSituation).filter(
        models.FiscalSituation.client_id == client_id,
        models.FiscalSituation.year == year,
    ).first()
    if not situation:
        raise HTTPException(status_code=404, detail="Situation fiscale introuvable")

    db.delete(situation)  # cascade sur les 3 tables enfants
    db.commit()
    return {"status": "deleted"}


@router.get("/admin/clients/{client_id}/fiscal-status/years", response_model=List[int])
def admin_list_fiscal_years(
    client_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth_utils.require_admin),
):
    """Annees pour lesquelles une situation fiscale existe deja pour ce client
    (pour peupler le filtre annee cote front)."""
    rows = (
        db.query(models.FiscalSituation.year)
        .filter(models.FiscalSituation.client_id == client_id)
        .order_by(models.FiscalSituation.year.desc())
        .all()
    )
    return [r[0] for r in rows]


# ---------- Client ----------

@router.get("/client/fiscal-status", response_model=schemas.FiscalSituationOut)
def client_get_fiscal_status(
    year: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    year = year or date.today().year
    return _get_fiscal_situation_or_404(db, current_user.id, year)


@router.get("/client/fiscal-status/years", response_model=List[int])
def client_list_fiscal_years(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    rows = (
        db.query(models.FiscalSituation.year)
        .filter(models.FiscalSituation.client_id == current_user.id)
        .order_by(models.FiscalSituation.year.desc())
        .all()
    )
    return [r[0] for r in rows]