from __future__ import annotations

from typing import Any

from sqlalchemy import text

from src.common.db import get_engine


DEFAULT_WEIGHTS = {
    "power": 0.25,
    "heat_offtake": 0.20,
    "climate": 0.15,
    "connectivity": 0.15,
    "commercial": 0.25,
}

DEFAULT_EXCLUSIONS = {
    "natura2000": True,
    "protected": True,
    "floodplain": True,
    "heritage": True,
    "airport": True,
    "military": True,
    "steep_slope": True,
    "seveso": True,
    "water_protected": True,
    "urban_industrial": True,
    "sami_reindeer": True,
}


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    merged = {**DEFAULT_WEIGHTS, **weights}
    total = sum(max(v, 0.0) for v in merged.values())
    if total <= 0:
        return DEFAULT_WEIGHTS
    return {k: max(v, 0.0) / total for k, v in merged.items()}


def fetch_scores(
    weights: dict[str, float],
    exclusions: dict[str, bool],
    bbox: tuple[float, float, float, float] | None = None,
    limit_n: int = 30000,
) -> list[dict[str, Any]]:
    w = normalize_weights(weights)
    ex = {**DEFAULT_EXCLUSIONS, **exclusions}
    bbox_params = bbox or (None, None, None, None)
    engine = get_engine()
    sql = text(
        """
        SELECT s.h3_index, s.score, s.coverage
        FROM score_cells(
          CAST(:weights AS JSONB),
          CAST(:exclusions AS JSONB),
          :west, :south, :east, :north,
          :limit_n
        ) s
        JOIN grid_cells g ON g.h3_index = s.h3_index
        WHERE s.score IS NOT NULL
        """
    )
    with engine.begin() as conn:
        rows = conn.execute(
            sql,
            {
                "weights": __import__("json").dumps(w),
                "exclusions": __import__("json").dumps(ex),
                "west": bbox_params[0],
                "south": bbox_params[1],
                "east": bbox_params[2],
                "north": bbox_params[3],
                "limit_n": limit_n,
            },
        ).mappings().all()
    return [dict(row) for row in rows]


def fetch_top_candidates(weights: dict[str, float], exclusions: dict[str, bool], top_n: int = 50) -> list[dict[str, Any]]:
    w = normalize_weights(weights)
    ex = {**DEFAULT_EXCLUSIONS, **exclusions}
    engine = get_engine()
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                  c.h3_index,
                  c.score,
                  c.coverage,
                  g.country,
                  g.bidding_zone,
                  g.municipality_code,
                  ST_Y(ST_Centroid(g.geom_4326)) AS lat,
                  ST_X(ST_Centroid(g.geom_4326)) AS lon,
                  COALESCE(m.municipality_name, 'Unknown area') AS municipality_name,
                  (
                    COALESCE(m.municipality_name, 'Unknown area')
                    || ', ' || g.country
                    || ' (' || COALESCE(g.bidding_zone, 'n/a') || ')'
                  ) AS candidate_name
                FROM top_candidate_cells(CAST(:weights AS JSONB), CAST(:exclusions AS JSONB), :top_n) c
                JOIN grid_cells g ON g.h3_index = c.h3_index
                LEFT JOIN municipality_lookup m ON m.municipality_code = g.municipality_code
                ORDER BY c.score DESC
                """
            ),
            {"weights": __import__("json").dumps(w), "exclusions": __import__("json").dumps(ex), "top_n": top_n},
        ).mappings().all()
    return [dict(row) for row in rows]
