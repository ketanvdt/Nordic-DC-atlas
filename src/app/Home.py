from __future__ import annotations

import h3
import pandas as pd
import pydeck as pdk
import streamlit as st
from sqlalchemy import text

from src.app.components.freshness_panel import render_freshness_panel
from src.app.components.panels import exclusion_panel, weight_panel
from src.app.services.overlays import get_overlay_mtime, load_municipality_overlay, load_roads_overlay
from src.app.services.scenarios import list_scenarios, save_scenario
from src.common.db import get_engine
from src.score.service import fetch_scores, fetch_top_candidates


def _to_map_df(scores: list[dict]) -> pd.DataFrame:
    rows = []
    for item in scores:
        lat, lon = h3.cell_to_latlng(item["h3_index"])
        rows.append({"h3_index": item["h3_index"], "score": item["score"], "lat": lat, "lon": lon})
    return pd.DataFrame(rows)


def _top_n_map_df(top_rows: list[dict], n: int = 10, selected_h3: set[str] | None = None) -> pd.DataFrame:
    rows = []
    selected_h3 = selected_h3 or set()
    for rank, item in enumerate(top_rows[:n], start=1):
        lat = float(item.get("lat") or 0.0)
        lon = float(item.get("lon") or 0.0)
        if lat == 0.0 and lon == 0.0:
            lat, lon = h3.cell_to_latlng(item["h3_index"])
        rows.append(
            {
                "rank": rank,
                "h3_index": item["h3_index"],
                "score": item["score"],
                "lat": lat,
                "lon": lon,
                "rank_label": f"#{rank}",
                "candidate_name": item.get("candidate_name", item["h3_index"]),
                "is_selected": item["h3_index"] in selected_h3,
            }
        )
    return pd.DataFrame(rows)


def _load_cell_details(h3_index: str) -> dict:
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT * FROM grid_cells WHERE h3_index = :h3"),
            {"h3": h3_index},
        ).mappings().first()
    return dict(row) if row else {}


def _h3_polygon(h3_index: str) -> list[list[float]]:
    boundary = [[lng, lat] for lat, lng in h3.cell_to_boundary(h3_index)]
    if boundary and boundary[0] != boundary[-1]:
        boundary.append(boundary[0])
    return boundary


def main() -> None:
    st.set_page_config(page_title="Nordic Site Atlas", layout="wide")
    st.title("Nordic Data Center Site Atlas (v1)")
    st.caption("Directional suitability tool for SE/NO/FI. Local v1 build with transparent known gaps.")

    weights = weight_panel()
    exclusions = exclusion_panel()
    st.sidebar.subheader("Map Overlays")
    show_municipalities = st.sidebar.checkbox("Municipality boundaries", value=True)
    show_roads = st.sidebar.checkbox("Road connections", value=True)
    show_grid = st.sidebar.checkbox("Grid outlines", value=False)
    roads_opacity = st.sidebar.slider("Road opacity", 10, 255, 120, 5)
    muni_opacity = st.sidebar.slider("Municipality opacity", 10, 255, 80, 5)

    st.sidebar.subheader("Quick Filters")
    min_score = st.sidebar.slider("Minimum score", 0.0, 1.0, 0.0, 0.01)
    focus_mode = st.sidebar.checkbox("Focus mode (dim non-selected)", value=False)

    col1, col2 = st.columns([2, 1])
    with col1:
        score_rows = fetch_scores(weights, exclusions, limit_n=15000)
        top = fetch_top_candidates(weights, exclusions, top_n=50)
        top_df = pd.DataFrame(top)

        country_options = sorted([c for c in top_df.get("country", pd.Series(dtype=str)).dropna().unique().tolist()])
        zone_options = sorted([z for z in top_df.get("bidding_zone", pd.Series(dtype=str)).dropna().unique().tolist()])
        selected_countries = st.sidebar.multiselect("Countries", country_options, default=country_options)
        selected_zones = st.sidebar.multiselect("Bidding zones", zone_options, default=zone_options)

        if not top_df.empty:
            top_df = top_df[top_df["score"] >= min_score]
            if selected_countries:
                top_df = top_df[top_df["country"].isin(selected_countries)]
            if selected_zones:
                top_df = top_df[top_df["bidding_zone"].isin(selected_zones)]

        name_to_h3 = {
            f"#{i+1} {row['candidate_name']}": row["h3_index"]
            for i, (_, row) in enumerate(top_df.head(20).iterrows())
        } if not top_df.empty else {}
        selected_names = st.multiselect("Highlight candidates", list(name_to_h3.keys()), default=list(name_to_h3.keys())[:1])
        selected_h3 = {name_to_h3[name] for name in selected_names if name in name_to_h3}

        map_df = _to_map_df(score_rows)
        map_df = map_df[map_df["score"] >= min_score]
        top10_df = _top_n_map_df(top_df.to_dict("records"), n=10, selected_h3=selected_h3)
        if map_df.empty:
            st.warning("No scored cells found. Run migrations, seed grid, characterize, and refresh normalized view.")
        else:
            score_alpha = 60 if focus_mode and selected_h3 else 150
            score_layer = pdk.Layer(
                "ScatterplotLayer",
                data=map_df,
                get_position="[lon, lat]",
                get_radius=350,
                get_fill_color=f"[255 - score*255, 150, score*255, {score_alpha}]",
                pickable=True,
            )
            top10_layer = pdk.Layer(
                "ScatterplotLayer",
                data=top10_df,
                get_position="[lon, lat]",
                get_radius=1100,
                get_fill_color=[255, 215, 0, 240],
                get_line_color=[30, 30, 30, 255],
                line_width_min_pixels=2,
                stroked=True,
                filled=True,
                pickable=True,
            )
            selected_layer = pdk.Layer(
                "ScatterplotLayer",
                data=top10_df[top10_df["is_selected"]] if not top10_df.empty else top10_df,
                get_position="[lon, lat]",
                get_radius=2500,
                get_fill_color=[0, 0, 0, 0],
                get_line_color=[255, 80, 80, 255],
                line_width_min_pixels=3,
                stroked=True,
                filled=False,
                pickable=False,
            )
            top10_label_layer = pdk.Layer(
                "TextLayer",
                data=top10_df,
                get_position="[lon, lat]",
                get_text="rank_label",
                get_size=14,
                get_color=[20, 20, 20, 255],
                get_alignment_baseline="'center'",
                get_text_anchor="'middle'",
                pickable=False,
            )
            center_lat = float(top10_df[top10_df["is_selected"]]["lat"].mean()) if selected_h3 and not top10_df[top10_df["is_selected"]].empty else 63.0
            center_lon = float(top10_df[top10_df["is_selected"]]["lon"].mean()) if selected_h3 and not top10_df[top10_df["is_selected"]].empty else 16.0
            zoom = 6.0 if selected_h3 else 3.4
            view_state = pdk.ViewState(latitude=center_lat, longitude=center_lon, zoom=zoom)

            layers: list[pdk.Layer] = [score_layer, top10_layer, selected_layer, top10_label_layer]

            municipality_path = "data/processed/municipalities.gpkg"
            municipalities_geojson = (
                load_municipality_overlay(municipality_path, get_overlay_mtime(municipality_path))
                if show_municipalities
                else None
            )
            if show_municipalities:
                if municipalities_geojson:
                    layers.append(
                        pdk.Layer(
                            "GeoJsonLayer",
                            data=municipalities_geojson,
                            stroked=True,
                            filled=False,
                            get_line_color=[40, 90, 170, muni_opacity],
                            line_width_min_pixels=1,
                            pickable=True,
                        )
                    )
                else:
                    st.info("Municipality overlay unavailable or unreadable at `data/processed/municipalities.gpkg`.")

            roads_path = "data/processed/roads.gpkg"
            roads_geojson = load_roads_overlay(roads_path, get_overlay_mtime(roads_path)) if show_roads else None
            if show_roads:
                if roads_geojson:
                    layers.append(
                        pdk.Layer(
                            "GeoJsonLayer",
                            data=roads_geojson,
                            stroked=True,
                            filled=False,
                            get_line_color=[90, 90, 90, roads_opacity],
                            line_width_min_pixels=1,
                            pickable=False,
                        )
                    )
                else:
                    st.info("Road overlay unavailable or unreadable at `data/processed/roads.gpkg`.")

            if show_grid:
                grid_df = top10_df.copy()
                grid_df["poly"] = grid_df["h3_index"].apply(_h3_polygon)
                layers.append(
                    pdk.Layer(
                        "PolygonLayer",
                        data=grid_df,
                        get_polygon="poly",
                        get_line_color=[35, 35, 35, 160],
                        get_fill_color=[0, 0, 0, 0],
                        line_width_min_pixels=1,
                        stroked=True,
                        filled=False,
                        pickable=False,
                    )
                )

            st.pydeck_chart(
                pdk.Deck(
                    layers=layers,
                    initial_view_state=view_state,
                    tooltip={"text": "name: {candidate_name}\nh3: {h3_index}\nscore: {score}\nrank: {rank}"},
                )
            )
            st.caption("Top 10 are gold, selected candidates get a red halo, overlays are configurable in the sidebar.")
            st.markdown("**Legend:** score dots (green-blue ramp) | top10 (gold) | selected (red ring)")

            st.subheader("Top Candidates")
            table_df = top_df.copy()
            if not table_df.empty:
                table_df.insert(0, "rank", range(1, len(table_df) + 1))
                table_df["score"] = table_df["score"].round(3)
            display_cols = [c for c in ["rank", "candidate_name", "score", "country", "bidding_zone"] if c in table_df.columns]
            st.dataframe(table_df[display_cols], use_container_width=True, hide_index=True)

    with col2:
        st.subheader("Scenario Saver")
        scenario_name = st.text_input("Name", value="Internal default scenario")
        scenario_desc = st.text_area("Description", value="Default grouped weights for v1")
        if st.button("Save scenario"):
            save_scenario(scenario_name, scenario_desc, weights, exclusions)
            st.success("Scenario saved")

        st.subheader("Saved Scenarios")
        scenarios = list_scenarios()
        if scenarios:
            scenario_df = pd.DataFrame(scenarios)
            st.dataframe(scenario_df[["name", "description", "updated_at"]], use_container_width=True, hide_index=True)
        else:
            st.info("No saved scenarios yet.")

        st.subheader("Cell Inspector")
        default_inspect = list(selected_h3)[0] if "selected_h3" in locals() and selected_h3 else ""
        h3_input = st.text_input("Inspect H3 index", value=default_inspect)
        if h3_input:
            details = _load_cell_details(h3_input.strip())
            if details:
                st.json(details)
            else:
                st.warning("Cell not found.")

        render_freshness_panel()

        st.subheader("Known gaps")
        st.markdown(
            "- Grid-capacity layer is directional (zone-level proxy).\n"
            "- DH and municipal receptivity contain manual coding.\n"
            "- Fiber backbone coverage is incomplete.\n"
            "- Final shortlist requires DSO queue + permit checks."
        )


if __name__ == "__main__":
    main()
