Deployment assets for `finance.ozodbek-akramov.uz`.

- `finance-backend.service`: systemd unit for the FastAPI backend
- `nginx.finance.ozodbek-akramov.uz.conf`: nginx site config exposing the backend at `/api`
- `remote_deploy_finance_backend.sh`: remote backend release activator used by GitHub Actions

Frontend deployment assets live in `frontend/`:

- `serve.mjs`: Node launcher for the TanStack Start build output
- `deploy/finance-frontend.service`: systemd unit for the frontend service

GitHub Actions secrets expected by `.github/workflows/deploy.yml`:

- `SSH_PRIVATE_KEY`

The workflow also supports the older Finance-specific secret names:

- `FINANCE_SERVER_HOST` (optional, defaults to `195.133.66.192`)
- `FINANCE_SERVER_PORT` (optional, defaults to `22`)
- `FINANCE_SERVER_USER` (optional, defaults to `root`)
- `FINANCE_SERVER_SSH_KEY` (fallback if `SSH_PRIVATE_KEY` is not set)

## Deploy Context Safety

Do not deploy the raw development bundle. It may contain `_incoming_projects/`, `exports/`, `logs/`, `reports/`, zip archives, local databases, Excel files, caches, pycache, and frontend `node_modules/`. `_incoming_projects/` is dev-only reference material for adapters and contracts; it must never be copied into a production image or release artifact.

Scan the filtered backend deploy context, not the raw workspace. A safe staging command is:

```bash
rm -rf /tmp/finance-backend-deploy-context
mkdir -p /tmp/finance-backend-deploy-context
rsync -a \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.pytest_cache/' \
  --exclude='.mypy_cache/' \
  --exclude='.ruff_cache/' \
  --exclude='.venv/' \
  --exclude='_incoming_projects/' \
  --exclude='*_extracted/' \
  --exclude='source/' \
  --exclude='audit-bundle-final/' \
  --exclude='audit_*/' \
  --exclude='audit-*/' \
  --exclude='/exports/' \
  --exclude='logs/' \
  --exclude='reports/' \
  --exclude='reports/**/source/' \
  --exclude='frontend/node_modules/' \
  --exclude='frontend/.next/' \
  --exclude='*.zip' \
  --exclude='*.db' \
  --exclude='*.sqlite' \
  --exclude='*.sqlite3' \
  --exclude='*.xls' \
  --exclude='*.xlsx' \
  --exclude='*.log' \
  app alembic deploy docs scripts tests pyproject.toml alembic.ini README.md AGENTS.md .dockerignore .gitignore \
  /tmp/finance-backend-deploy-context/
python scripts/check_deploy_artifact_safety.py --root /tmp/finance-backend-deploy-context --max-results 100
```

The raw workspace may still fail the scanner by design. A production Docker/build context must exclude incoming zips, logs, reports, local DB/SQLite files, Excel files, caches, pycache, and generated export/audit data. `app/modules/exports/` is source code and is intentionally allowed.
