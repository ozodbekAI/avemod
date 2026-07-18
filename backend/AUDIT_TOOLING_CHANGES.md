# Audit Tooling Changes

## 2026-06-23

- Fixed `scripts/check_deploy_artifact_safety.py` so source audit scripts under `scripts/audit_*.py` are allowed in the clean deploy-context scan.
- The scanner still blocks generated audit bundles, audit directories, raw report snapshots, archives, local databases, logs, exports, and nested/generated `audit_*` paths.
- Extended `scripts/run_full_runtime_endpoint_audit.py` to include prompt-required evidence manifests in the audit bundle:
  - `00_repo_inventory/source_manifest.json`
  - `00_repo_inventory/module_file_map.md`
  - `00_repo_inventory/route_file_map.md`
  - `db/migration_manifest.md`
  - `MODULE_STATE_CONSISTENCY_REPORT.md`
  - `AUDIT_TOOLING_CHANGES.md`

