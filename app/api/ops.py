from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Passenger
from app.models.enums import PassengerTier
from app.schemas.ops import PassengerCreate, PassengerOut, ReconciliationOut
from app.services.reconciliation import reconcile

router = APIRouter(tags=["ops"])


@router.post("/passengers", response_model=PassengerOut, status_code=201)
def create_passenger(payload: PassengerCreate, db: Session = Depends(get_db)):
    p = Passenger(name=payload.name, tier=PassengerTier(payload.tier))
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.get("/reconciliation", response_model=ReconciliationOut)
def reconciliation(db: Session = Depends(get_db)):
    report = reconcile(db)
    return ReconciliationOut(ok=report.ok, flights=report.flights)