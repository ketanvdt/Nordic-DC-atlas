from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from src.common.db import get_engine


def list_scenarios() -> list[dict[str, Any]]:
    engine = get_engine()
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id::text, name, description, weights, exclusions_active, updated_at
                FROM scenarios
                ORDER BY updated_at DESC
                """
            )
        ).mappings().all()
    return [dict(r) for r in rows]


def save_scenario(name: str, description: str, weights: dict[str, float], exclusions: dict[str, bool]) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO scenarios (name, description, weights, exclusions_active)
                VALUES (:name, :description, CAST(:weights AS JSONB), CAST(:exclusions AS JSONB))
                """
            ),
            {"name": name, "description": description, "weights": json.dumps(weights), "exclusions": json.dumps(exclusions)},
        )
