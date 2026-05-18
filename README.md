# FHIR Resource Explorer

An interactive FHIR R4 data explorer with live HAPI FHIR server queries and SYNTHEA patient data visualization.

## Live Demo

https://pdanso1-health-portfolio-fhir-explorer.streamlit.app

---

## Clinical Context

### What is FHIR and Why Does It Matter?

FHIR (Fast Healthcare Interoperability Resources) is HL7's current standard for healthcare data exchange. FHIR R4 (released 2019) was the first normative release and is now mandated by CMS for all payers and providers under 45 CFR Part 156.

FHIR replaces older HL7 standards:
- **HL7 v2** (1987): Pipe-delimited flat files with no standardized data types. Implementation varies by vendor, requiring expensive custom integrations for every system pair.
- **HL7 v3**: XML-based and theoretically comprehensive, but so architecturally complex it was rarely implemented fully.
- **FHIR R4**: REST APIs + JSON/XML + standardized US Core profiles = a standard that is actually implementable by modern developers.

### Key Resource Types (Clinically)

| Resource | Clinical Meaning | Common Use Cases |
|---|---|---|
| Patient | Demographics (synthetic) | Eligibility, enrollment, care management |
| Observation | Lab results, vitals, measurements | Quality measures (HbA1c, BP), risk stratification |
| Condition | Diagnoses, problem list | HEDIS denominators, chronic disease registries |
| MedicationRequest | Prescribed and dispensed medications | Medication reconciliation, adherence monitoring |
| Encounter | Clinical visits and interactions | Utilization management, network adequacy |

### Why FHIR Replaced HL7 v2 and v3

- **HL7 v2** was created for point-to-point messaging in 1987. Every hospital implemented it differently, so HL7 v2 from Epic looks different from HL7 v2 from Cerner — requiring custom interfaces for every connection.
- **HL7 v3** tried to solve this with a universal Reference Information Model (RIM), but the resulting XML schemas were so complex that few organizations implemented them fully, and implementations were rarely interoperable.
- **FHIR R4** changed the paradigm: REST + JSON + explicit profiles (US Core) means any FHIR-compliant system can exchange data with any other FHIR-compliant system without custom middleware.
- CMS mandated FHIR R4 APIs by 2021 under the Interoperability and Patient Access Rule (45 CFR Part 156), requiring all CMS-regulated payers to expose member data via FHIR APIs.

### Real-World Uses of FHIR

- **Patient Portals**: Apple Health, Google Health, and Epic MyChart all use FHIR R4 APIs to pull patient records from health systems.
- **Payer-Provider Exchange**: The HL7 Da Vinci Project uses FHIR for Prior Authorization, Coverage Requirements Discovery, and clinical data exchange between payers and providers.
- **Quality Reporting**: FHIR-based electronic Clinical Quality Measures (eCQMs) are replacing legacy QRDA XML submissions for CMS quality programs.
- **Clinical Decision Support**: CDS Hooks is a FHIR-based standard that delivers real-time alerts and recommendations within EHR workflows at the point of care.
- **Research and Apps**: SMART on FHIR allows third-party applications to launch directly inside EHR systems with OAuth2-scoped access to patient data.

### Why FHIR Knowledge Matters for Clinical Informatics

You cannot work on interoperability, care quality, population health, or value-based care analytics without understanding FHIR. It is the plumbing that modern healthcare data runs through. Every CMS quality program, every payer-provider data exchange, and every patient-facing health app now depends on FHIR R4.

---

## App Features

1. **Resource Browser** — Browse FHIR resources from bundled SYNTHEA synthetic patient data or query a live HAPI FHIR public server. Filter by resource type and explore raw JSON structures.

2. **Patient-Centric View** — Full patient summary in one view: demographics, active conditions, recent lab results, current medications, and a chronological visit timeline.

3. **FHIR Query Builder** — Construct and execute FHIR search queries interactively. Select resource type, add search parameters, and see the generated FHIR URL alongside paginated results. Useful for understanding how FHIR REST search works.

4. **Relationship Diagram** — Network graph (Plotly) showing how a patient's resources are connected — how an Encounter links to Observations, Conditions, and MedicationRequests. Illustrates the reference-based data model of FHIR.

5. **FHIR Concepts Reference** — A reference panel explaining FHIR terminology (Bundle, Resource, Reference, Profile, CodeSystem, ValueSet) for team members and stakeholders who are not FHIR-fluent.

---

## Data Sources

- **SYNTHEA sample data** (default mode): 10 synthetic patient bundles are included in `data/sample/`. All data is fully synthetic — no real patient information, no PHI. Synthea is an open-source synthetic patient generator maintained by MITRE Corporation.
- **HAPI FHIR public server** (live mode): `https://hapi.fhir.org/baseR4` is a shared HL7 test server used by the FHIR developer community. Response times vary (3–10 seconds) depending on server load. This is expected behavior for a public test environment — not an app performance issue.

---

## Stack

| Component | Technology |
|---|---|
| UI | Streamlit |
| Data manipulation | pandas |
| HTTP / FHIR REST | requests |
| Visualization | Plotly |
| Language | Python 3.10+ |

---

## Setup

```bash
git clone https://github.com/pdanso1/health-portfolio-fhir-explorer
cd health-portfolio-fhir-explorer
pip install -r requirements.txt
streamlit run app.py
```

App runs locally on port **8505** (configured in `.streamlit/config.toml`). No API keys required — HAPI FHIR is a public server and SYNTHEA data is bundled.

---

## About

Built by **Paa Danso**, Medical Lab Scientist II with an M.S. in Biological Data Science, transitioning into healthcare data analytics and clinical informatics. This app is part of a healthcare analytics portfolio demonstrating practical skills in FHIR data access, clinical data modeling, and health data visualization.

Portfolio: https://pdanso1-health-portfolio-fhir-explorer.streamlit.app
