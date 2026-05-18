"""
FHIR R4 bundle parser — converts SYNTHEA JSON bundles into pandas DataFrames.
"""

from __future__ import annotations

import json
import os
import glob
from typing import Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def load_bundle(path: str) -> dict:
    """Load a FHIR JSON bundle from *path*. Returns parsed dict or {} on error."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def get_entries_by_type(bundle: dict, resource_type: str) -> list[dict]:
    """Extract all resources of *resource_type* from a bundle's entry array."""
    return [
        e["resource"]
        for e in bundle.get("entry", [])
        if e.get("resource", {}).get("resourceType") == resource_type
    ]


def _strip_date(datetime_str: str) -> str:
    """Trim an ISO-8601 datetime to date-only (first 10 characters)."""
    return (datetime_str or "")[:10]


def _patient_id_from_reference(reference: str) -> str:
    """Strip the 'urn:uuid:' prefix from a subject reference."""
    return reference.replace("urn:uuid:", "") if reference else ""


def _obs_value(resource: dict):
    """Return (value, unit) from an Observation resource, trying multiple value[x] fields."""
    vq = resource.get("valueQuantity")
    if vq is not None:
        return vq.get("value"), vq.get("unit", "")

    vs = resource.get("valueString")
    if vs is not None:
        return vs, ""

    vc = resource.get("valueCodeableConcept")
    if vc is not None:
        return vc.get("text", ""), ""

    return None, ""


# ---------------------------------------------------------------------------
# Single-bundle extractors
# ---------------------------------------------------------------------------

def extract_patient(bundle: dict) -> dict:
    """Extract patient demographics from a bundle.

    Returns a flat dict with keys: id, name, birth_date, gender, city, state.
    Returns an empty dict if no Patient resource is found.
    """
    resources = get_entries_by_type(bundle, "Patient")
    if not resources:
        return {}

    r = resources[0]

    # Name — prefer 'official' use, fall back to first entry
    names = r.get("name", [])
    name_entry = next(
        (n for n in names if n.get("use") == "official"),
        names[0] if names else {},
    )
    given = name_entry.get("given", [""])
    first = given[0] if given else ""
    full_name = f"{first} {name_entry.get('family', '')}".strip()

    # Address
    addresses = r.get("address", [])
    addr = addresses[0] if addresses else {}

    return {
        "id": r.get("id", ""),
        "name": full_name,
        "birth_date": r.get("birthDate", ""),
        "gender": r.get("gender", ""),
        "city": addr.get("city", ""),
        "state": addr.get("state", ""),
    }


def extract_patients(bundles: list[dict]) -> pd.DataFrame:
    """Extract patient demographics from a list of bundles.

    Columns: id, name, birth_date, gender, city, state
    """
    rows = [extract_patient(b) for b in bundles]
    rows = [r for r in rows if r]  # drop empty dicts
    return pd.DataFrame(rows, columns=["id", "name", "birth_date", "gender", "city", "state"])


def extract_observations(bundle: dict) -> pd.DataFrame:
    """Extract Observation resources from a bundle.

    Columns: id, patient_id, date, test_name, value, unit, status
    """
    rows = []
    for r in get_entries_by_type(bundle, "Observation"):
        subject_ref = r.get("subject", {}).get("reference", "")
        patient_id = _patient_id_from_reference(subject_ref)

        code = r.get("code", {})
        # Prefer code.text; fall back to first coding display
        test_name = code.get("text") or (
            code.get("coding", [{}])[0].get("display", "")
        )

        value, unit = _obs_value(r)

        rows.append({
            "id": r.get("id", ""),
            "patient_id": patient_id,
            "date": _strip_date(r.get("effectiveDateTime", "")),
            "test_name": test_name,
            "value": value,
            "unit": unit,
            "status": r.get("status", ""),
        })

    return pd.DataFrame(rows, columns=["id", "patient_id", "date", "test_name", "value", "unit", "status"])


def extract_conditions(bundle: dict) -> pd.DataFrame:
    """Extract Condition resources from a bundle.

    Columns: id, patient_id, condition, status, onset_date
    """
    rows = []
    for r in get_entries_by_type(bundle, "Condition"):
        subject_ref = r.get("subject", {}).get("reference", "")
        patient_id = _patient_id_from_reference(subject_ref)

        condition = r.get("code", {}).get("text", "")

        status = (
            r.get("clinicalStatus", {})
            .get("coding", [{}])[0]
            .get("code", "unknown")
        )

        onset = r.get("onsetDateTime", "") or r.get("onsetPeriod", {}).get("start", "")

        rows.append({
            "id": r.get("id", ""),
            "patient_id": patient_id,
            "condition": condition,
            "status": status,
            "onset_date": _strip_date(onset),
        })

    return pd.DataFrame(rows, columns=["id", "patient_id", "condition", "status", "onset_date"])


def extract_medications(bundle: dict) -> pd.DataFrame:
    """Extract MedicationRequest resources from a bundle.

    Columns: id, patient_id, medication, status, authored_date
    """
    rows = []
    for r in get_entries_by_type(bundle, "MedicationRequest"):
        subject_ref = r.get("subject", {}).get("reference", "")
        patient_id = _patient_id_from_reference(subject_ref)

        # Try medicationCodeableConcept first, then medicationReference display
        med_cc = r.get("medicationCodeableConcept", {})
        medication = med_cc.get("text") or med_cc.get("coding", [{}])[0].get("display", "")
        if not medication:
            med_ref = r.get("medicationReference", {})
            medication = med_ref.get("display", "")

        rows.append({
            "id": r.get("id", ""),
            "patient_id": patient_id,
            "medication": medication,
            "status": r.get("status", ""),
            "authored_date": _strip_date(r.get("authoredOn", "")),
        })

    return pd.DataFrame(rows, columns=["id", "patient_id", "medication", "status", "authored_date"])


def extract_encounters(bundle: dict) -> pd.DataFrame:
    """Extract Encounter resources from a bundle.

    Columns: id, patient_id, type, class_code, start_date, end_date, status
    """
    rows = []
    for r in get_entries_by_type(bundle, "Encounter"):
        subject_ref = r.get("subject", {}).get("reference", "")
        patient_id = _patient_id_from_reference(subject_ref)

        types = r.get("type", [])
        enc_type = types[0].get("text", "") if types else ""

        enc_class = r.get("class", {})
        class_code = enc_class.get("code", "")

        period = r.get("period", {})
        start_date = _strip_date(period.get("start", ""))
        end_date = _strip_date(period.get("end", ""))

        rows.append({
            "id": r.get("id", ""),
            "patient_id": patient_id,
            "type": enc_type,
            "class_code": class_code,
            "start_date": start_date,
            "end_date": end_date,
            "status": r.get("status", ""),
        })

    return pd.DataFrame(rows, columns=["id", "patient_id", "type", "class_code", "start_date", "end_date", "status"])


# ---------------------------------------------------------------------------
# Multi-bundle loaders
# ---------------------------------------------------------------------------

def load_all_bundles(sample_dir: str) -> list[dict]:
    """Load all JSON files from *sample_dir*.

    Returns a list of bundle dicts.  Each bundle has ``_filename`` set to the
    base filename so callers can track provenance.
    """
    bundles = []
    pattern = os.path.join(sample_dir, "*.json")
    for filepath in sorted(glob.glob(pattern)):
        bundle = load_bundle(filepath)
        if bundle:
            bundle["_filename"] = os.path.basename(filepath)
            bundles.append(bundle)
    return bundles


def get_patient_bundle(sample_dir: str, patient_name: str) -> Optional[dict]:
    """Find the bundle whose patient name contains *patient_name* (case-insensitive).

    Returns the matching bundle dict, or None if not found.
    """
    search = patient_name.lower()
    for bundle in load_all_bundles(sample_dir):
        patient = extract_patient(bundle)
        if search in patient.get("name", "").lower():
            return bundle
    return None
