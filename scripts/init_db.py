"""Create the collector schema, standardized tables, and official weights table."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

from scripts.config import LOGS_TABLE, METADATA_TABLE, SCHEMA_NAME, TIME_SERIES_TABLE, WEIGHTS_TABLE
from scripts.db import build_engine

CREATE_SCHEMA = f"CREATE SCHEMA IF NOT EXISTS {SCHEMA_NAME}"
CREATE_METADATA_TABLE = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA_NAME}.{METADATA_TABLE} (
    series_id VARCHAR(200) NOT NULL,
    name VARCHAR(500) NOT NULL,
    description VARCHAR(2000),
    country VARCHAR(3) NOT NULL,
    frequency VARCHAR(20),
    unit VARCHAR(50),
    first_observation DATE,
    last_observation DATE,
    observation_count INTEGER NOT NULL,
    eco_group VARCHAR(250),
    source_url VARCHAR(1000) NOT NULL,
    last_publish_date DATE,
    collected_at TIMESTAMP NOT NULL,
    CONSTRAINT pk_metadata PRIMARY KEY (series_id)
)
"""
CREATE_TIME_SERIES_TABLE = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA_NAME}.{TIME_SERIES_TABLE} (
    series_id VARCHAR(200) NOT NULL,
    reference_date DATE NOT NULL,
    vintage_date DATE NOT NULL,
    value DOUBLE NOT NULL,
    collected_at TIMESTAMP NOT NULL,
    CONSTRAINT pk_time_series PRIMARY KEY (series_id, reference_date, vintage_date)
)
"""
CREATE_WEIGHTS_TABLE = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA_NAME}.{WEIGHTS_TABLE} (
    series_id VARCHAR(200) NOT NULL,
    reference_date DATE NOT NULL,
    vintage_date DATE NOT NULL,
    weight DOUBLE NOT NULL,
    collected_at TIMESTAMP NOT NULL,
    CONSTRAINT pk_weights PRIMARY KEY (series_id, reference_date, vintage_date)
)
"""
CREATE_LOGS_TABLE = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA_NAME}.{LOGS_TABLE} (
    id BIGINT GENERATED ALWAYS AS IDENTITY,
    started_at TIMESTAMP NOT NULL,
    finished_at TIMESTAMP NOT NULL,
    status VARCHAR(20) NOT NULL,
    log_text VARCHAR(65535) NOT NULL,
    traceback VARCHAR(65535),
    CONSTRAINT pk_logs PRIMARY KEY (id)
)
"""


def init_db(engine: Engine) -> None:
    """Create all database objects idempotently."""
    with engine.begin() as conn:
        for statement in (
            CREATE_SCHEMA,
            CREATE_METADATA_TABLE,
            CREATE_TIME_SERIES_TABLE,
            CREATE_WEIGHTS_TABLE,
            CREATE_LOGS_TABLE,
        ):
            conn.execute(text(statement))


if __name__ == "__main__":
    init_db(build_engine())
