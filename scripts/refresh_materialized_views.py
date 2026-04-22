from __future__ import annotations

import os

from sqlalchemy import create_engine, text


def main() -> None:
    db_url = os.getenv("DATABASE_URL", "postgresql+psycopg://atlas:atlas@localhost:5432/atlas")
    engine = create_engine(db_url, future=True)
    with engine.begin() as conn:
        conn.execute(text("REFRESH MATERIALIZED VIEW grid_cells_normalized;"))
        print("refreshed grid_cells_normalized")


if __name__ == "__main__":
    main()
