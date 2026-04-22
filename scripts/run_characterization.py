from __future__ import annotations

from src.characterize.dh_tiers import apply_dh_tiers
from src.characterize.exclusions import run_all_exclusions
from src.characterize.power_layers import run as run_power_layers
from src.characterize.soft_features import populate_placeholder_soft_features


def main() -> None:
    run_power_layers()
    apply_dh_tiers()
    populate_placeholder_soft_features()
    run_all_exclusions()
    print("Characterization complete")


if __name__ == "__main__":
    main()
