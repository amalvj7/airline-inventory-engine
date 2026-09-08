import pytest

from app.config import Settings

PSYCOPG = "postgresql+psycopg://u:p@h:5432/db"


@pytest.mark.parametrize(
    "given",
    [
        "postgres://u:p@h:5432/db",          # what Render / Railway / Neon hand out
        "postgresql://u:p@h:5432/db",        # driverless: SQLAlchemy would pick psycopg2
        "postgresql+psycopg://u:p@h:5432/db",  # already correct, must pass through
    ],
)
def test_database_url_is_normalised_to_the_psycopg_driver(given):
    s = Settings(database_url=given, _env_file=None)
    assert s.database_url == PSYCOPG


def test_test_database_url_is_normalised_too():
    s = Settings(database_url=PSYCOPG, test_database_url="postgres://x/y", _env_file=None)
    assert s.test_database_url == "postgresql+psycopg://x/y"


def test_pool_sizes_default_and_read_from_env(monkeypatch):
    assert Settings(database_url=PSYCOPG, _env_file=None).db_pool_size == 20

    monkeypatch.setenv("DB_POOL_SIZE", "5")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "2")
    s = Settings(database_url=PSYCOPG, _env_file=None)
    assert (s.db_pool_size, s.db_max_overflow) == (5, 2)
