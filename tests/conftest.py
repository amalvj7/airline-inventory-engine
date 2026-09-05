import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.config import settings
from app.database import Base

TEST_URL = settings.test_database_url or settings.database_url


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(TEST_URL, pool_size=25, max_overflow=10, future=True)
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture(scope="session")
def Session(engine):
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@pytest.fixture(autouse=True)
def clean_db(engine):
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE booking_legs, bookings, flight_inventory, flights, passengers "
                "RESTART IDENTITY CASCADE"
            )
        )
    yield