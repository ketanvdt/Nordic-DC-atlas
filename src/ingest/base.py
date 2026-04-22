from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import httpx
from sqlalchemy import text

from src.common.db import get_engine
from src.common.settings import settings


@dataclass
class SourceArtifact:
    source_key: str
    source_url: str
    local_path: Path
    checksum: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_if_changed(source_key: str, source_url: str, out_name: str) -> SourceArtifact:
    raw_dir = Path(settings.raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_path = raw_dir / out_name
    response = httpx.get(source_url, timeout=60)
    response.raise_for_status()
    out_path.write_bytes(response.content)
    checksum = sha256_file(out_path)
    return SourceArtifact(source_key=source_key, source_url=source_url, local_path=out_path, checksum=checksum)


def record_source(artifact: SourceArtifact, license_name: str = "unknown", metadata: dict | None = None) -> bool:
    metadata = metadata or {}
    engine = get_engine()
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT checksum FROM data_sources WHERE source_key = :source_key"),
            {"source_key": artifact.source_key},
        ).scalar_one_or_none()
        if existing == artifact.checksum:
            return False

        conn.execute(
            text(
                """
                INSERT INTO data_sources (source_key, source_url, license, checksum, metadata)
                VALUES (:source_key, :source_url, :license, :checksum, CAST(:metadata AS JSONB))
                ON CONFLICT (source_key)
                DO UPDATE SET
                  source_url = EXCLUDED.source_url,
                  license = EXCLUDED.license,
                  checksum = EXCLUDED.checksum,
                  metadata = EXCLUDED.metadata,
                  fetched_at = NOW()
                """
            ),
            {
                "source_key": artifact.source_key,
                "source_url": artifact.source_url,
                "license": license_name,
                "checksum": artifact.checksum,
                "metadata": __import__("json").dumps(metadata),
            },
        )
    return True
