"""
FHIR resource relationship graph — builds a Plotly network diagram showing
how a patient's FHIR resources are interconnected.
"""

from __future__ import annotations

import math

import plotly.graph_objects as go

from fhir.parser import (
    extract_patient,
    extract_conditions,
    extract_observations,
    extract_encounters,
    extract_medications,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_COLORS = {
    "Patient": "#0066CC",
    "Condition": "#FF8C00",
    "Observation": "#228B22",
    "Encounter": "#8B008B",
    "Medication": "#DC143C",
}

_SIZES = {
    "Patient": 30,
    "Condition": 20,
    "Observation": 20,
    "Encounter": 20,
    "Medication": 20,
}

_MAX_LABEL_LEN = 20
_EDGE_COLOR = "rgba(160, 160, 160, 0.6)"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _truncate(text: str, max_len: int = _MAX_LABEL_LEN) -> str:
    """Truncate *text* to *max_len* characters, appending '…' if cut."""
    text = str(text) if text is not None else ""
    return text if len(text) <= max_len else text[:max_len - 1] + "…"


def _circular_positions(
    center_x: float,
    center_y: float,
    radius: float,
    start_angle: float,
    n_nodes: int,
) -> list[tuple[float, float]]:
    """Return (x, y) positions arranged in an arc of *n_nodes* points.

    Positions are spaced 15 degrees apart starting from *start_angle* (degrees).
    """
    positions: list[tuple[float, float]] = []
    for i in range(n_nodes):
        angle = math.radians(start_angle + i * 15)
        x = center_x + radius * math.cos(angle)
        y = center_y + radius * math.sin(angle)
        positions.append((x, y))
    return positions


def _edge_trace(x0: float, y0: float, x1: float, y1: float) -> go.Scatter:
    """Return a thin gray line trace from (x0, y0) to (x1, y1)."""
    return go.Scatter(
        x=[x0, x1, None],
        y=[y0, y1, None],
        mode="lines",
        line=dict(color=_EDGE_COLOR, width=1.5),
        hoverinfo="none",
        showlegend=False,
    )


def _node_trace(
    xs: list[float],
    ys: list[float],
    labels: list[str],
    hovers: list[str],
    resource_type: str,
) -> go.Scatter:
    """Return a markers+text scatter trace for a set of resource nodes."""
    return go.Scatter(
        x=xs,
        y=ys,
        mode="markers+text",
        text=labels,
        textposition="top center",
        hovertext=hovers,
        hoverinfo="text",
        marker=dict(
            color=_COLORS[resource_type],
            size=_SIZES[resource_type],
            line=dict(color="white", width=1.5),
        ),
        showlegend=False,
        name=resource_type,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_patient_graph(bundle: dict) -> go.Figure:
    """Build a Plotly network diagram for a patient's FHIR resources.

    Layout
    ------
    - Patient node at center (large, blue)
    - Up to 5 most recent Conditions (amber/orange), top-left arc
    - Up to 5 most recent Observations (green), top-right arc
    - Up to 5 most recent Encounters (purple), bottom-right arc
    - Up to 3 active Medications (crimson), bottom-left arc

    Returns
    -------
    plotly.graph_objects.Figure
    """
    # ---- Extract patient info ------------------------------------------------
    patient = extract_patient(bundle)
    patient_name = patient.get("name", "Unknown Patient")
    patient_hover = (
        f"<b>{patient_name}</b><br>"
        f"DOB: {patient.get('birth_date', 'N/A')}<br>"
        f"Gender: {patient.get('gender', 'N/A')}<br>"
        f"Location: {patient.get('city', '')}, {patient.get('state', '')}"
    )

    traces: list[go.BaseTraceType] = []

    # ---- Extract and filter resource DataFrames ------------------------------
    cond_df = extract_conditions(bundle)
    obs_df = extract_observations(bundle)
    enc_df = extract_encounters(bundle)
    med_df = extract_medications(bundle)

    # Conditions — sort by onset_date desc, take up to 5
    if not cond_df.empty:
        cond_df = (
            cond_df
            .sort_values("onset_date", ascending=False, na_position="last")
            .head(5)
            .reset_index(drop=True)
        )

    # Observations — sort by date desc, take up to 5
    if not obs_df.empty:
        obs_df = (
            obs_df
            .sort_values("date", ascending=False, na_position="last")
            .head(5)
            .reset_index(drop=True)
        )

    # Encounters — sort by start_date desc, take up to 5
    if not enc_df.empty:
        enc_df = (
            enc_df
            .sort_values("start_date", ascending=False, na_position="last")
            .head(5)
            .reset_index(drop=True)
        )

    # Medications — prefer active status, take up to 3
    if not med_df.empty:
        active = med_df[med_df["status"] == "active"]
        med_df = (active if not active.empty else med_df).head(3).reset_index(drop=True)

    # ---- Check for empty state -----------------------------------------------
    all_empty = (
        cond_df.empty and obs_df.empty and enc_df.empty and med_df.empty
    )

    if all_empty:
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=[0],
                y=[0],
                mode="markers+text",
                text=[_truncate(patient_name)],
                textposition="top center",
                hovertext=[patient_hover],
                hoverinfo="text",
                marker=dict(color=_COLORS["Patient"], size=_SIZES["Patient"]),
                showlegend=False,
            )
        )
        fig.add_annotation(
            x=0,
            y=-0.3,
            text="No FHIR resources found in this bundle.",
            showarrow=False,
            font=dict(size=13, color="gray"),
        )
        _apply_layout(fig, patient_name)
        return fig

    # ---- Build resource sectors ----------------------------------------------
    radius = 1.8

    # (resource_type, df, label_col, hover_builder, start_angle)
    sectors = [
        ("Condition",   cond_df, "condition",  _cond_hover,  130),
        ("Observation", obs_df,  "test_name",   _obs_hover,    40),
        ("Encounter",   enc_df,  "type",        _enc_hover,   310),
        ("Medication",  med_df,  "medication",  _med_hover,   210),
    ]

    for resource_type, df, label_col, hover_fn, start_angle in sectors:
        if df.empty:
            continue

        n = len(df)
        positions = _circular_positions(0, 0, radius, start_angle, n)

        node_xs: list[float] = []
        node_ys: list[float] = []
        node_labels: list[str] = []
        node_hovers: list[str] = []

        for i, row in df.iterrows():
            x, y = positions[i]
            # Edge: patient centre → node
            traces.append(_edge_trace(0, 0, x, y))
            node_xs.append(x)
            node_ys.append(y)
            node_labels.append(_truncate(row.get(label_col, "")))
            node_hovers.append(hover_fn(row))

        traces.append(
            _node_trace(node_xs, node_ys, node_labels, node_hovers, resource_type)
        )

    # ---- Patient node (always last so it renders on top) ---------------------
    traces.append(
        go.Scatter(
            x=[0],
            y=[0],
            mode="markers+text",
            text=[_truncate(patient_name)],
            textposition="top center",
            hovertext=[patient_hover],
            hoverinfo="text",
            marker=dict(
                color=_COLORS["Patient"],
                size=_SIZES["Patient"],
                line=dict(color="white", width=2),
            ),
            showlegend=False,
            name="Patient",
        )
    )

    fig = go.Figure(data=traces)
    _apply_layout(fig, patient_name)
    return fig


# ---------------------------------------------------------------------------
# Layout helper
# ---------------------------------------------------------------------------

def _apply_layout(fig: go.Figure, patient_name: str) -> None:
    """Apply standard axes-hidden layout to *fig*."""
    fig.update_layout(
        showlegend=False,
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        hovermode="closest",
        margin=dict(l=20, r=20, t=40, b=20),
        height=500,
        title=f"Resource Relationships: {patient_name}",
        plot_bgcolor="white",
    )


# ---------------------------------------------------------------------------
# Hover-text builders
# ---------------------------------------------------------------------------

def _cond_hover(row) -> str:
    return (
        f"<b>Condition</b><br>"
        f"{row.get('condition', 'N/A')}<br>"
        f"Status: {row.get('status', 'N/A')}<br>"
        f"Onset: {row.get('onset_date', 'N/A')}"
    )


def _obs_hover(row) -> str:
    value = row.get("value", "")
    unit = row.get("unit", "")
    value_str = f"{value} {unit}".strip() if value is not None else "N/A"
    return (
        f"<b>Observation</b><br>"
        f"{row.get('test_name', 'N/A')}<br>"
        f"Value: {value_str}<br>"
        f"Date: {row.get('date', 'N/A')}"
    )


def _enc_hover(row) -> str:
    return (
        f"<b>Encounter</b><br>"
        f"{row.get('type', 'N/A')}<br>"
        f"Class: {row.get('class_code', 'N/A')}<br>"
        f"Start: {row.get('start_date', 'N/A')}"
    )


def _med_hover(row) -> str:
    return (
        f"<b>Medication</b><br>"
        f"{row.get('medication', 'N/A')}<br>"
        f"Status: {row.get('status', 'N/A')}<br>"
        f"Authored: {row.get('authored_date', 'N/A')}"
    )
