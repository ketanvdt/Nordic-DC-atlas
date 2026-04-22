from __future__ import annotations

import streamlit as st

from src.app.services.freshness import LayerStatus, build_report, summary_counts


_STATE_EMOJI = {"real": "✅", "placeholder": "⚠️", "missing": "⛔"}
_STATE_LABEL = {
    "real": "Real data",
    "placeholder": "Placeholder (random)",
    "missing": "Not ingested",
}


def render_freshness_panel() -> None:
    st.subheader("Data freshness")
    try:
        report = build_report()
    except Exception as exc:  # pragma: no cover
        st.error(f"Could not load freshness report: {exc!r}")
        return

    counts = summary_counts(report)
    total = sum(counts.values())
    st.caption(
        f"{counts['real']} real / {counts['placeholder']} placeholder / {counts['missing']} missing "
        f"(of {total} layers). Placeholder values still drive the score — treat rankings "
        f"as directional until everything is real."
    )

    with st.expander("Per-layer source status", expanded=False):
        for kind in ("exclusion", "feature"):
            st.markdown(f"**{kind.capitalize()} layers**")
            layers = [layer for layer in report if layer.kind == kind]
            for layer in layers:
                _render_layer_row(layer)
            st.markdown("---")


def _render_layer_row(layer: LayerStatus) -> None:
    emoji = _STATE_EMOJI.get(layer.state, "?")
    state_label = _STATE_LABEL.get(layer.state, layer.state)
    st.markdown(
        f"{emoji} **{layer.label}** — *{state_label}*  \n"
        f"<span style='color:#555'>{layer.source}</span>  \n"
        f"<span style='color:#777;font-size:0.85em'>{layer.details}</span>",
        unsafe_allow_html=True,
    )
