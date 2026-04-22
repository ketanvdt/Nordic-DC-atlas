from __future__ import annotations

import streamlit as st

from src.score.service import DEFAULT_EXCLUSIONS, DEFAULT_WEIGHTS, normalize_weights


def weight_panel() -> dict[str, float]:
    st.sidebar.subheader("Feature Weights")
    power = st.sidebar.slider("Power", 0.0, 1.0, float(DEFAULT_WEIGHTS["power"]), 0.01)
    heat = st.sidebar.slider("Heat offtake", 0.0, 1.0, float(DEFAULT_WEIGHTS["heat_offtake"]), 0.01)
    climate = st.sidebar.slider("Climate and cooling", 0.0, 1.0, float(DEFAULT_WEIGHTS["climate"]), 0.01)
    connectivity = st.sidebar.slider("Connectivity", 0.0, 1.0, float(DEFAULT_WEIGHTS["connectivity"]), 0.01)
    commercial = st.sidebar.slider("Commercial", 0.0, 1.0, float(DEFAULT_WEIGHTS["commercial"]), 0.01)
    return normalize_weights(
        {
            "power": power,
            "heat_offtake": heat,
            "climate": climate,
            "connectivity": connectivity,
            "commercial": commercial,
        }
    )


def exclusion_panel() -> dict[str, bool]:
    st.sidebar.subheader("Exclusions")
    values = {}
    for key, default in DEFAULT_EXCLUSIONS.items():
        values[key] = st.sidebar.checkbox(key.replace("_", " ").title(), value=default)
    return values
