from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Passenger
from app.schemas.ops import PassengerCreate, PassengerOut, ReconciliationOut
from app.services.reconciliation import reconcile

router = APIRouter(tags=["ops"])


@router.post("/passengers", response_model=PassengerOut, status_code=201)
def create_passenger(payload: PassengerCreate, db: Session = Depends(get_db)):
    p = Passenger(name=payload.name, tier=payload.tier)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.get("/passengers", response_model=list[PassengerOut])
def list_passengers(
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    # deliberately flat: this fills a picker, so it never loads Passenger.bookings
    stmt = select(Passenger).order_by(Passenger.name).limit(limit).offset(offset)
    return db.execute(stmt).scalars().all()


@router.get("/reconciliation", response_model=ReconciliationOut)
def reconciliation(db: Session = Depends(get_db)):
    report = reconcile(db)
    return ReconciliationOut(ok=report.ok, flights=report.flights)