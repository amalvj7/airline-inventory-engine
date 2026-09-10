from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.schemas.demo import RaceOut, RaceRequest
from app.services.exceptions import DemoDisabled
from app.services.race import RaceGroup, run_race

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/race", response_model=RaceOut)
def race(payload: RaceRequest, db: Session = Depends(get_db)):
    """Fire N simultaneous booking attempts and report the outcome.

    `groups` races several itineraries against each other -- the shared-leg case.
    `flight_id` + `clients` is shorthand for one cohort on a single flight.

    Writes real bookings: this demonstrates the engine, it does not simulate it.
    Disable with DEMO_ENDPOINTS_ENABLED=false.
    """
    if not settings.demo_endpoints_enabled:
        raise DemoDisabled()

    if payload.groups:
        groups = [
            RaceGroup(flight_ids=g.flight_ids, clients=g.clients, label=g.label)
            for g in payload.groups
        ]
    else:
        groups = [RaceGroup(flight_ids=[payload.flight_id], clients=payload.clients)]

    return run_race(db, groups)
