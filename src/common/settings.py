from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "postgresql+psycopg://atlas:atlas@localhost:5432/atlas")
    raw_dir: str = os.getenv("RAW_DATA_DIR", "data/raw")
    processed_dir: str = os.getenv("PROCESSED_DATA_DIR", "data/processed")
    grid_dir: str = os.getenv("GRID_DATA_DIR", "data/grid")
    study_bbox_4326: tuple[float, float, float, float] = (4.5, 54.0, 33.0, 72.5)


settings = Settings()
