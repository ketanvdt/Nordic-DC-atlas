from __future__ import annotations

from sqlalchemy import create_engine

from src.common.settings import settings


def get_engine():
    return create_engine(settings.database_url, future=True)
