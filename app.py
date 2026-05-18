"""
FHIR Resource Explorer — Streamlit app (port 8505)

Five tabs:
  1. Resource Browser   — SYNTHEA local data or HAPI FHIR live server
  2. Patient View       — per-patient demographics + resource drill-down
  3. Query Builder      — interactive FHIR URL builder + live query runner
  4. Relationship Diagram — Plotly network graph for a chosen patient
  5. FHIR Concepts      — static reference / educational content
"""

from __future__ import annotations

import json
import os
from typing import Optional

import pandas as pd
import streamlit as st

from fhir.parser import (
    extract_conditions,
    extract_encounters,
    extract_medications,
    extract_observations,
    extract_patient,
    extract_patients,
    load_all_bundles,
)
from fhir.client import build_fhir_url, search_resources
from fhir.relationships import build_patient_graph

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="FHIR Resource Explorer",
    page_icon="🏥",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SAMPLE_DIR = os.path.join(os.path.dirname(__file__), "data", "sample")
PAGE_SIZE = 10

SEARCH_PARAMS: dict[str, list[str]] = {
    "Patient": ["family", "birthdate", "gender"],
    "Observation": ["patient", "code", "date"],
    "Condition": ["patient", "clinical-status"],
    "MedicationRequest": ["patient", "status"],
    "Encounter": ["patient", "date", "class"],
}

SEARCH_PARAM_LABELS: dict[str, list[str]] = {
    "Patient": ["family (last name)", "birthdate", "gender"],
    "Observation": ["patient (ID)", "code (LOINC)", "date"],
    "Condition": ["patient (ID)", "clinical-status"],
    "MedicationRequest": ["patient (ID)", "status"],
    "Encounter": ["patient (ID)", "date", "class"],
}

# ---------------------------------------------------------------------------
# Cached data loading
# ---------------------------------------------------------------------------


@st.cache_data
def load_sample_data() -> list[dict]:
    """Load all SYNTHEA bundles once and cache them."""
    return load_all_bundles(SAMPLE_DIR)


@st.cache_data
def get_patient_names(bundles_tuple) -> list[str]:
    """Return sorted patient names from the cached bundles."""
    # Accept a tuple (hashable) but work with the underlying list
    bundles = list(bundles_tuple)
    patients_df = extract_patients(bundles)
    names = sorted(patients_df["name"].dropna().tolist())
    return names


def _bundles_as_tuple(bundles: list[dict]):
    """Convert bundle list to a hashable form for cache_data compatibility."""
    # We cache using the filenames as a stable key
    return tuple(b.get("_filename", "") for b in bundles)


# ---------------------------------------------------------------------------
# Helper: paginate a DataFrame
# ---------------------------------------------------------------------------


def _paginate(df: pd.DataFrame, page_key: str) -> pd.DataFrame:
    """Show paginated view of *df* with Prev/Next buttons.

    Uses ``st.session_state[page_key]`` to track current page.
    Returns the slice for the current page.
    """
    total = len(df)
    n_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    if page_key not in st.session_state:
        st.session_state[page_key] = 0

    page = st.session_state[page_key]
    page = max(0, min(page, n_pages - 1))
    st.session_state[page_key] = page

    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    slice_df = df.iloc[start:end]

    col_prev, col_info, col_next = st.columns([1, 2, 1])
    with col_prev:
        if st.button("← Prev", key=f"{page_key}_prev", disabled=(page == 0)):
            st.session_state[page_key] = page - 1
            st.rerun()
    with col_info:
        st.markdown(
            f"<div style='text-align:center; padding-top:6px;'>Page {page + 1} of {n_pages} "
            f"({total} rows)</div>",
            unsafe_allow_html=True,
        )
    with col_next:
        if st.button("Next →", key=f"{page_key}_next", disabled=(page >= n_pages - 1)):
            st.session_state[page_key] = page + 1
            st.rerun()

    return slice_df


# ---------------------------------------------------------------------------
# Helper: bundle lookup by patient name
# ---------------------------------------------------------------------------


def _get_bundle_by_name(bundles: list[dict], name: str) -> Optional[dict]:
    """Return the bundle whose patient name matches *name* exactly."""
    for bundle in bundles:
        patient = extract_patient(bundle)
        if patient.get("name") == name:
            return bundle
    return None


# ---------------------------------------------------------------------------
# Tab 1 — Resource Browser
# ---------------------------------------------------------------------------


def _tab_resource_browser(bundles: list[dict]) -> None:
    st.subheader("Resource Browser")

    mode = st.radio(
        "Data Source",
        ["SYNTHEA Sample Data", "HAPI FHIR Server (Live)"],
        horizontal=True,
        key="rb_mode",
    )

    resource_type = st.selectbox(
        "Resource Type",
        ["Patient", "Observation", "Condition", "MedicationRequest", "Encounter"],
        key="rb_resource_type",
    )

    st.markdown("---")

    if mode == "SYNTHEA Sample Data":
        _rb_synthea(bundles, resource_type)
    else:
        _rb_hapi(resource_type)


def _rb_synthea(bundles: list[dict], resource_type: str) -> None:
    """Resource Browser — SYNTHEA mode."""
    # Build combined DataFrame across all bundles
    if resource_type == "Patient":
        df = extract_patients(bundles)
    elif resource_type == "Observation":
        frames = [extract_observations(b) for b in bundles]
        df = pd.concat([f for f in frames if not f.empty], ignore_index=True) if frames else pd.DataFrame()
    elif resource_type == "Condition":
        frames = [extract_conditions(b) for b in bundles]
        df = pd.concat([f for f in frames if not f.empty], ignore_index=True) if frames else pd.DataFrame()
    elif resource_type == "MedicationRequest":
        frames = [extract_medications(b) for b in bundles]
        df = pd.concat([f for f in frames if not f.empty], ignore_index=True) if frames else pd.DataFrame()
    else:  # Encounter
        frames = [extract_encounters(b) for b in bundles]
        df = pd.concat([f for f in frames if not f.empty], ignore_index=True) if frames else pd.DataFrame()

    if df.empty:
        st.info("No data found.")
        return

    st.caption(f"Loaded **{len(df)}** {resource_type} records from 10 SYNTHEA bundles.")

    # Paginated table
    page_slice = _paginate(df, f"rb_page_{resource_type}")
    st.dataframe(page_slice, use_container_width=True)

    # Row detail view
    st.markdown("#### Row Detail")
    if resource_type == "Patient":
        detail_label = "name"
    elif resource_type == "Observation":
        detail_label = "test_name"
    elif resource_type == "Condition":
        detail_label = "condition"
    elif resource_type == "MedicationRequest":
        detail_label = "medication"
    else:
        detail_label = "type"

    # Show names/labels from the *current page* only
    row_options = page_slice[detail_label].fillna("(unknown)").tolist()
    row_indices = page_slice.index.tolist()
    label_to_idx = {lbl: idx for idx, lbl in zip(row_indices, row_options)}

    selected_label = st.selectbox(
        "Select a row to inspect",
        options=["— select —"] + row_options,
        key=f"rb_detail_{resource_type}",
    )

    if selected_label != "— select —":
        selected_idx = label_to_idx.get(selected_label)
        if selected_idx is not None:
            row = df.loc[selected_idx]
            st.info(
                "  \n".join(f"**{col}:** {row[col]}" for col in df.columns)
            )
            with st.expander("Raw FHIR JSON (row as dict)"):
                st.json(row.to_dict())


def _rb_hapi(resource_type: str) -> None:
    """Resource Browser — HAPI FHIR Server mode."""
    st.warning(
        "⚠️ Querying HAPI FHIR public test server — response time may vary (3–10 seconds)."
    )

    patient_id = st.text_input(
        "Patient ID filter (optional — leave blank to search all)",
        key="rb_hapi_patient_id",
    )

    if st.button("Search", key="rb_hapi_search"):
        params: dict = {}
        if patient_id.strip():
            params["patient"] = patient_id.strip()

        with st.spinner(f"Querying HAPI FHIR for {resource_type}…"):
            result = search_resources(resource_type, params if params else None, count=10)

        if result is None:
            st.error("No response from HAPI FHIR server. Check your connection or try again later.")
            return

        # Build table from entries
        entries = result.get("entry", [])
        if not entries:
            st.info("No results returned.")
        else:
            rows = []
            for e in entries:
                res = e.get("resource", {})
                rows.append({
                    "id": res.get("id", ""),
                    "resourceType": res.get("resourceType", ""),
                    "status": res.get("status", ""),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True)

        with st.expander("Raw JSON Response"):
            st.json(result)


# ---------------------------------------------------------------------------
# Tab 2 — Patient-Centric View
# ---------------------------------------------------------------------------


def _tab_patient_view(bundles: list[dict]) -> None:
    st.subheader("Patient-Centric View")

    patients_df = extract_patients(bundles)
    patient_names = sorted(patients_df["name"].dropna().tolist())

    selected_name = st.selectbox(
        "Select a patient",
        options=["— select a patient —"] + patient_names,
        key="pv_patient",
    )

    if selected_name == "— select a patient —":
        st.info("Choose a patient from the dropdown to explore their clinical data.")
        return

    bundle = _get_bundle_by_name(bundles, selected_name)
    if bundle is None:
        st.error("Could not load bundle for this patient.")
        return

    patient = extract_patient(bundle)
    conditions_df = extract_conditions(bundle)
    observations_df = extract_observations(bundle)
    medications_df = extract_medications(bundle)
    encounters_df = extract_encounters(bundle)

    # ---- Demographics card ---------------------------------------------------
    st.markdown("### Demographics")
    d_col1, d_col2, d_col3, d_col4 = st.columns(4)
    with d_col1:
        st.metric("Name", patient.get("name", "N/A"))
    with d_col2:
        st.metric("Date of Birth", patient.get("birth_date", "N/A"))
    with d_col3:
        st.metric("Gender", patient.get("gender", "N/A").capitalize())
    with d_col4:
        location = f"{patient.get('city', '')} {patient.get('state', '')}".strip()
        st.metric("Location", location or "N/A")

    # ---- Resource counts -----------------------------------------------------
    st.markdown("### Resource Counts")
    rc_col1, rc_col2, rc_col3, rc_col4 = st.columns(4)
    with rc_col1:
        st.metric("Conditions", len(conditions_df))
    with rc_col2:
        st.metric("Observations", len(observations_df))
    with rc_col3:
        st.metric("Medications", len(medications_df))
    with rc_col4:
        st.metric("Encounters", len(encounters_df))

    st.markdown("---")

    # ---- Conditions ----------------------------------------------------------
    st.markdown("### Conditions")
    if conditions_df.empty:
        st.info("No conditions found.")
    else:
        st.caption("Note: Active conditions shown in green, resolved in gray (status column).")
        st.dataframe(conditions_df.drop(columns=["id", "patient_id"], errors="ignore"), use_container_width=True)

    # ---- Recent lab results --------------------------------------------------
    st.markdown("### Recent Lab Results (last 10 observations)")
    if observations_df.empty:
        st.info("No observations found.")
    else:
        recent_obs = (
            observations_df
            .sort_values("date", ascending=False, na_position="last")
            .head(10)
        )
        st.dataframe(
            recent_obs[["date", "test_name", "value", "unit", "status"]],
            use_container_width=True,
        )

    # ---- Active medications --------------------------------------------------
    st.markdown("### Active Medications")
    if medications_df.empty:
        st.info("No medications found.")
    else:
        active_meds = medications_df[medications_df["status"] == "active"]
        if active_meds.empty:
            st.info("No active medications on record.")
        else:
            st.dataframe(
                active_meds[["medication", "status", "authored_date"]],
                use_container_width=True,
            )

    # ---- Timeline ------------------------------------------------------------
    st.markdown("### Clinical Timeline")
    timeline_rows = []

    for _, row in encounters_df.iterrows():
        timeline_rows.append({
            "date": row.get("start_date", ""),
            "type": "Encounter",
            "description": row.get("type", ""),
            "detail": row.get("class_code", ""),
        })

    for _, row in conditions_df.iterrows():
        timeline_rows.append({
            "date": row.get("onset_date", ""),
            "type": "Condition",
            "description": row.get("condition", ""),
            "detail": row.get("status", ""),
        })

    for _, row in observations_df.sort_values("date", ascending=False).head(10).iterrows():
        value = row.get("value", "")
        unit = row.get("unit", "")
        timeline_rows.append({
            "date": row.get("date", ""),
            "type": "Observation",
            "description": row.get("test_name", ""),
            "detail": f"{value} {unit}".strip() if value is not None else "",
        })

    if timeline_rows:
        timeline_df = (
            pd.DataFrame(timeline_rows)
            .dropna(subset=["date"])
            .sort_values("date", ascending=False)
            .reset_index(drop=True)
        )
        st.dataframe(timeline_df, use_container_width=True)
    else:
        st.info("No timeline events found.")


# ---------------------------------------------------------------------------
# Tab 3 — FHIR Query Builder
# ---------------------------------------------------------------------------


def _tab_query_builder() -> None:
    st.subheader("FHIR Query Builder")

    resource_type = st.selectbox(
        "Resource Type",
        list(SEARCH_PARAMS.keys()),
        key="qb_resource_type",
    )

    # Dynamic parameter inputs
    params = SEARCH_PARAMS[resource_type]
    labels = SEARCH_PARAM_LABELS[resource_type]

    st.markdown("#### Search Parameters")
    param_values: dict[str, str] = {}
    for param, label in zip(params, labels):
        val = st.text_input(
            label.capitalize(),
            key=f"qb_param_{resource_type}_{param}",
            placeholder="leave blank to skip",
        )
        if val.strip():
            param_values[param] = val.strip()

    col_build, col_run = st.columns([1, 1])

    constructed_url = build_fhir_url(resource_type, param_values if param_values else None)

    with col_build:
        if st.button("Build Query", key="qb_build"):
            st.session_state["qb_url"] = constructed_url
            st.session_state["qb_show_url"] = True

    with col_run:
        run_clicked = st.button("Run Query", key="qb_run")

    # Always show the constructed URL once built
    if st.session_state.get("qb_show_url") or run_clicked:
        url_to_show = st.session_state.get("qb_url", constructed_url)
        st.markdown("#### Constructed FHIR URL")
        st.code(url_to_show, language="text")
        st.info("💡 Copy the URL above to test directly in your browser")

    if run_clicked:
        st.session_state["qb_url"] = constructed_url
        st.session_state["qb_show_url"] = True
        st.warning("⚠️ Querying HAPI FHIR public test server — response time may vary (3–10 seconds).")

        with st.spinner("Querying HAPI FHIR server…"):
            result = search_resources(resource_type, param_values if param_values else None, count=10)

        if result is None:
            st.error("No response from HAPI FHIR server. Check your connection or try again later.")
            return

        # Parsed table
        entries = result.get("entry", [])
        if entries:
            rows = []
            for e in entries:
                res = e.get("resource", {})
                row: dict = {
                    "id": res.get("id", ""),
                    "resourceType": res.get("resourceType", ""),
                }
                # Add common fields by resource type
                if resource_type == "Patient":
                    names = res.get("name", [])
                    name_entry = names[0] if names else {}
                    given = name_entry.get("given", [""])
                    row["name"] = f"{given[0] if given else ''} {name_entry.get('family', '')}".strip()
                    row["birthDate"] = res.get("birthDate", "")
                    row["gender"] = res.get("gender", "")
                elif resource_type == "Observation":
                    code = res.get("code", {})
                    row["test_name"] = code.get("text") or (code.get("coding", [{}])[0].get("display", ""))
                    row["status"] = res.get("status", "")
                    row["date"] = res.get("effectiveDateTime", "")[:10] if res.get("effectiveDateTime") else ""
                elif resource_type == "Condition":
                    row["condition"] = res.get("code", {}).get("text", "")
                    row["status"] = (res.get("clinicalStatus", {}).get("coding", [{}])[0].get("code", ""))
                elif resource_type == "MedicationRequest":
                    med_cc = res.get("medicationCodeableConcept", {})
                    row["medication"] = med_cc.get("text") or med_cc.get("coding", [{}])[0].get("display", "")
                    row["status"] = res.get("status", "")
                elif resource_type == "Encounter":
                    enc_types = res.get("type", [])
                    row["type"] = enc_types[0].get("text", "") if enc_types else ""
                    row["status"] = res.get("status", "")
                rows.append(row)

            st.markdown("#### Results")
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
        else:
            st.info("No entries returned in the FHIR bundle.")

        with st.expander("Raw JSON Response"):
            st.json(result)


# ---------------------------------------------------------------------------
# Tab 4 — Relationship Diagram
# ---------------------------------------------------------------------------


def _tab_relationship_diagram(bundles: list[dict]) -> None:
    st.subheader("Patient Resource Relationship Diagram")

    patients_df = extract_patients(bundles)
    patient_names = sorted(patients_df["name"].dropna().tolist())

    selected_name = st.selectbox(
        "Select a patient",
        options=["— select a patient —"] + patient_names,
        key="rd_patient",
    )

    if selected_name == "— select a patient —":
        st.info("Choose a patient to visualize their FHIR resource relationships.")
        return

    bundle = _get_bundle_by_name(bundles, selected_name)
    if bundle is None:
        st.error("Could not load bundle for this patient.")
        return

    fig = build_patient_graph(bundle)
    st.plotly_chart(fig, use_container_width=True)

    # Legend
    st.markdown("#### Legend")
    legend_cols = st.columns(5)
    legend_items = [
        ("#0066CC", "Patient"),
        ("#FF8C00", "Condition"),
        ("#228B22", "Observation"),
        ("#8B008B", "Encounter"),
        ("#DC143C", "Medication"),
    ]
    for col, (color, label) in zip(legend_cols, legend_items):
        with col:
            st.markdown(
                f"<span style='display:inline-block;width:16px;height:16px;"
                f"background:{color};border-radius:50%;margin-right:6px;'></span>"
                f"**{label}**",
                unsafe_allow_html=True,
            )

    # Resource counts summary
    st.markdown("#### Resource Counts")
    conditions_df = extract_conditions(bundle)
    observations_df = extract_observations(bundle)
    medications_df = extract_medications(bundle)
    encounters_df = extract_encounters(bundle)

    rc1, rc2, rc3, rc4 = st.columns(4)
    with rc1:
        st.metric("Conditions", len(conditions_df))
    with rc2:
        st.metric("Observations", len(observations_df))
    with rc3:
        st.metric("Medications", len(medications_df))
    with rc4:
        st.metric("Encounters", len(encounters_df))


# ---------------------------------------------------------------------------
# Tab 5 — FHIR Concepts Reference
# ---------------------------------------------------------------------------


def _tab_fhir_concepts() -> None:
    st.markdown("""
## What is FHIR?

FHIR (Fast Healthcare Interoperability Resources) is the current standard for healthcare
data exchange, developed by HL7 International. FHIR R4 is what modern EHRs, payers, and
health apps use for data sharing under CMS interoperability mandates.

## Key Resource Types

| Resource | What it represents | Example |
|---|---|---|
| Patient | Demographic information | Name, DOB, gender, address |
| Observation | Clinical measurements and lab results | HbA1c 7.8%, BP 138/86, Body Weight |
| Condition | Diagnoses and problems | Type 2 diabetes, Hypertension |
| MedicationRequest | Prescribed medications | Metformin 500mg twice daily |
| Encounter | Clinical visits and interactions | Office visit 2022-03-15 |

## FHIR Bundle Structure

A FHIR Bundle is a container for multiple resources. SYNTHEA exports patient data as
transaction bundles where each `entry` in the `entry[]` array contains one resource.

```json
{
  "resourceType": "Bundle",
  "type": "transaction",
  "entry": [
    {"resource": {"resourceType": "Patient", "id": "...", ...}},
    {"resource": {"resourceType": "Condition", "id": "...", ...}}
  ]
}
```

## FHIR References

Resources reference each other using IDs. For example, an Observation's `subject.reference`
points to the Patient it belongs to: `"subject": {"reference": "urn:uuid:abc123"}`.

## FHIR Search Parameters

FHIR defines standard search parameters by resource type:
- **Token** (`code=4548-4`): exact match on codes (LOINC, SNOMED)
- **Date** (`date=ge2022-01-01`): date comparisons with prefixes (ge, le, gt, lt)
- **Reference** (`patient=123`): links to related resources
- **String** (`family=Smith`): name searches

## R4 vs R3 — What Changed?

FHIR R4 (2019) was the first "normative" release — meaning backwards-compatible and
stable for production use. Key changes from R3: mandatory patient consent framework,
improved MedicationRequest, standardized US Core profiles, mandatory support for
`application/fhir+json`.

## Real-World Uses

- **Patient portals** (Apple Health, Epic MyChart) use FHIR R4 APIs
- **CMS interoperability rules** mandate FHIR R4 APIs for all payers
- **Prior authorization** (CMS-0057) requires FHIR-based PA workflows by 2026
- **Clinical decision support** hooks integrate via CDS Hooks (FHIR-based)
""")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    st.title("🏥 FHIR Resource Explorer")
    st.caption(
        "Explore FHIR R4 data from 10 SYNTHEA synthetic patient bundles "
        "or query the public HAPI FHIR test server live."
    )

    # Load all SYNTHEA bundles once (cached)
    bundles = load_sample_data()

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📋 Resource Browser",
        "👤 Patient View",
        "🔍 Query Builder",
        "🕸️ Relationship Diagram",
        "📚 FHIR Concepts",
    ])

    with tab1:
        _tab_resource_browser(bundles)

    with tab2:
        _tab_patient_view(bundles)

    with tab3:
        _tab_query_builder()

    with tab4:
        _tab_relationship_diagram(bundles)

    with tab5:
        _tab_fhir_concepts()


if __name__ == "__main__":
    main()
