# Claims Factory Component Map

Date: 2026-06-22

## Finance-Owned Components

- API routes: `app/modules/portal/router.py`
- Local orchestration: `app/services/claims_factory.py`
- Detector adapter: `app/services/claims_adapter.py`
- Case templates: `app/services/claims_case_templates.py`
- Operator lifecycle models: `app/models/operator.py`
- Candidate/run models: `app/models/claims.py`
- API contracts: `app/schemas/claims.py`

## API Surface

- `GET /portal/cases`: list local claims cases.
- `POST /portal/cases`: create a local claims case.
- `POST /portal/cases/from-signal`: idempotently create a local case from an Action Center signal.
- `GET /portal/cases/detect/*`: read-only detector previews.
- `POST /portal/claims/scans`: run local detectors and persist candidates.
- `GET /portal/claims/scans`: list persisted detector runs.
- `GET /portal/claims/scans/{run_id}`: inspect one detector run.
- `POST /portal/claims/scans/{run_id}/retry`: rerun the same detector/period.
- `GET /portal/claims/candidates`: list persisted candidates.
- `GET /portal/claims/candidates/{candidate_id}`: inspect one candidate.
- `PATCH /portal/claims/candidates/{candidate_id}/status`: local candidate triage.
- `POST /portal/claims/candidates/{candidate_id}/create-case`: create/link a local `OperatorCase`.

## Detector Types

- `defect`
- `supply_discrepancy`
- `missing_goods`
- `report_anomaly`
- `compensation_underpayment`
- `repeat_claim`
- `pretrial`

`all` expands to the full set above.

## Legacy/External Reference Mapping

- Legacy `cases.py` lifecycle concepts map to `OperatorCase`, `OperatorEvidence`, `OperatorDraft`, and `ResultEvent`.
- Legacy compensation matching maps to detector output plus `claim_candidates.expected_amount`.
- Legacy finance trace concepts map to `claim_candidates.evidence_summary_json` and case payload `evidence_summary`.
- Legacy submit/apply operations are not mapped to an external action in MVP. They remain local manual records unless a future safe adapter is added.
