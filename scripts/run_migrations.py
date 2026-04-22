from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, text


def main() -> None:
    db_url = os.getenv("DATABASE_URL", "postgresql+psycopg://atlas:atlas@localhost:5432/atlas")
    engine = create_engine(db_url, future=True)
    migrations_dir = Path("sql/migrations")
    files = sorted(migrations_dir.glob("*.sql"))
    with engine.begin() as conn:
        for file in files:
            sql = file.read_text(encoding="utf-8")
            conn.execute(text(sql))
            print(f"applied {file.name}")


if __name__ == "__main__":
    main()
