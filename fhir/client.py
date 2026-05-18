"""
HAPI FHIR REST client — queries the public test server at https://hapi.fhir.org/baseR4.

The server is slow (3–10 seconds per request) and unreliable. Handles timeouts gracefully.
Used only when users explicitly switch to "HAPI FHIR Server" mode; defaults to SYNTHEA data.
"""

from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlencode

import requests

# Configuration
BASE_URL = "https://hapi.fhir.org/baseR4"
TIMEOUT = 15  # seconds

# Setup logging
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# URL Builder (no network calls)
# ---------------------------------------------------------------------------

def build_fhir_url(resource_type: str, params: dict = None) -> str:
    """
    Build a FHIR query URL string for display in the Query Builder UI.

    Does NOT make a network request. Returns a clean URL without _format=json
    so users can copy and paste it easily.

    Args:
        resource_type: "Patient", "Observation", "Condition", etc.
        params: FHIR search parameters dict (optional)

    Returns:
        Full FHIR query URL string.

    Examples:
        build_fhir_url("Patient", {"_count": "10"})
        → "https://hapi.fhir.org/baseR4/Patient?_count=10"

        build_fhir_url("Observation", {"patient": "123", "code": "4548-4"})
        → "https://hapi.fhir.org/baseR4/Observation?patient=123&code=4548-4"
    """
    url = f"{BASE_URL}/{resource_type}"

    if params:
        # Filter out None values and empty strings
        clean_params = {k: v for k, v in params.items() if v}
        if clean_params:
            url += "?" + urlencode(clean_params)

    return url


# ---------------------------------------------------------------------------
# Network requests
# ---------------------------------------------------------------------------

def search_resources(resource_type: str, params: dict = None, count: int = 10) -> Optional[dict]:
    """
    Search FHIR resources on HAPI server.

    Args:
        resource_type: "Patient", "Observation", "Condition", "MedicationRequest", "Encounter"
        params: FHIR search parameters dict (e.g., {"patient": "592911", "_count": "10"})
        count: number of results (added as _count param)

    Returns:
        FHIR Bundle dict (JSON response parsed) or None on error.

    Examples:
        search_resources("Patient", count=10)
        → GET https://hapi.fhir.org/baseR4/Patient?_count=10

        search_resources("Observation", {"patient": "592911"}, count=20)
        → GET https://hapi.fhir.org/baseR4/Observation?patient=592911&_count=20
    """
    try:
        # Build request parameters
        request_params = dict(params) if params else {}
        request_params["_count"] = count
        request_params["_format"] = "json"

        # Build URL
        url = f"{BASE_URL}/{resource_type}"

        # Make request with timeout and Accept header
        headers = {"Accept": "application/fhir+json"}
        response = requests.get(
            url,
            params=request_params,
            headers=headers,
            timeout=TIMEOUT,
        )

        # Raise for HTTP errors
        response.raise_for_status()

        # Return parsed JSON
        return response.json()

    except requests.exceptions.Timeout:
        logger.warning(f"HAPI FHIR request timed out after {TIMEOUT}s for {resource_type}")
        return None
    except requests.exceptions.ConnectionError:
        logger.warning("Cannot connect to HAPI FHIR server")
        return None
    except requests.exceptions.HTTPError as e:
        logger.warning(f"HAPI FHIR HTTP error: {e.response.status_code} for {resource_type}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error querying HAPI FHIR: {e}")
        return None


def get_resource(resource_type: str, resource_id: str) -> Optional[dict]:
    """
    Get a single FHIR resource by ID.

    Args:
        resource_type: "Patient", "Observation", "Condition", etc.
        resource_id: The resource's unique ID

    Returns:
        Parsed JSON dict or None on error.

    Example:
        get_resource("Patient", "592911")
        → GET https://hapi.fhir.org/baseR4/Patient/592911
    """
    try:
        url = f"{BASE_URL}/{resource_type}/{resource_id}"
        headers = {"Accept": "application/fhir+json"}

        response = requests.get(
            url,
            headers=headers,
            timeout=TIMEOUT,
        )

        response.raise_for_status()
        return response.json()

    except requests.exceptions.Timeout:
        logger.warning(f"HAPI FHIR request timed out after {TIMEOUT}s for {resource_type}/{resource_id}")
        return None
    except requests.exceptions.ConnectionError:
        logger.warning("Cannot connect to HAPI FHIR server")
        return None
    except requests.exceptions.HTTPError as e:
        logger.warning(f"HAPI FHIR HTTP error: {e.response.status_code} for {resource_type}/{resource_id}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error getting HAPI FHIR resource: {e}")
        return None


def get_patient_resources(patient_id: str, resource_type: str, count: int = 20) -> Optional[dict]:
    """
    Get all resources of a type for a specific patient.

    Shorthand for search_resources(resource_type, {"patient": patient_id}, count).

    Args:
        patient_id: The patient's unique ID
        resource_type: "Observation", "Condition", "MedicationRequest", "Encounter", etc.
        count: number of results (default 20)

    Returns:
        FHIR Bundle dict or None on error.

    Example:
        get_patient_resources("592911", "Observation", count=50)
        → GET https://hapi.fhir.org/baseR4/Observation?patient=592911&_count=50
    """
    return search_resources(resource_type, {"patient": patient_id}, count)
