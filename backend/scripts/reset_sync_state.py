from __future__ import annotations

import argparse
import json

from sqlalchemy import create_engine, text

from app.core.config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset sync cursor/run state for one domain")
    parser.add_argument("--account-id", type=int, required=True)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--cursor-key", default=None)
    args = parser.parse_args()

    engine = create_engine(get_settings().sync_database_url)
    with engine.begin() as conn:
        cursor_sql = """
            update wb_sync_cursors
            set status = 'idle',
                last_synced_at = now(),
                cursor_value = coalesce(cursor_value, '{}'::jsonb) || jsonb_build_object(
                    'manualResetAt', now()::text,
                    'manualReset', true
                )
            where account_id = :account_id
              and domain = :domain
        """
        params = {"account_id": args.account_id, "domain": args.domain}
        if args.cursor_key is not None:
            cursor_sql += " and cursor_key = :cursor_key"
            params["cursor_key"] = args.cursor_key
        cursor_result = conn.execute(text(cursor_sql), params)

        run_result = conn.execute(
            text(
                """
                update wb_sync_runs
                set status = 'failed',
                    finished_at = now(),
                    error_text = coalesce(error_text, 'Manually reset stale sync state')
                where account_id = :account_id
                  and domain = :domain
                  and status = 'running'
                """
            ),
            {"account_id": args.account_id, "domain": args.domain},
        )

    print(
        json.dumps(
            {
                "account_id": args.account_id,
                "domain": args.domain,
                "cursor_key": args.cursor_key,
                "reset_cursors": int(cursor_result.rowcount or 0),
                "reset_runs": int(run_result.rowcount or 0),
            }
        )
    )


if __name__ == "__main__":
    main()
