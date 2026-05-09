from __future__ import annotations

import json

from src.characterize.dh_tiers import apply_dh_tiers
from src.characterize.power_layers import run as run_power_layers
from src.characterize.real_ingest import run_all as run_registry_layers
from src.characterize.soft_features import populate_placeholder_soft_features


def main() -> None:
    run_power_layers()
    apply_dh_tiers()
    populate_placeholder_soft_features()
    report = run_registry_layers()
    print(json.dumps(report, indent=2))
    print("Characterization complete")


if __name__ == "__main__":
    main()
