from __future__ import annotations

from pathlib import Path

from scripts.scan_secret_leaks import scan_file


def test_secret_leak_scanner_flags_raw_token_print(tmp_path: Path) -> None:
    source = tmp_path / "unsafe.py"
    source.write_text(
        """
def main(access_token):
    print(f"access_token={access_token}")
""".strip()
        + "\n",
        encoding="utf-8",
    )

    findings = scan_file(source)

    assert len(findings) == 1
    assert findings[0].call == "print"
    assert findings[0].line == 2


def test_secret_leak_scanner_flags_raw_token_logger(tmp_path: Path) -> None:
    source = tmp_path / "unsafe_logger.py"
    source.write_text(
        """
def main(logger, refresh_token):
    logger.info("refresh_token=%s", refresh_token)
""".strip()
        + "\n",
        encoding="utf-8",
    )

    findings = scan_file(source)

    assert len(findings) == 1
    assert findings[0].call == "logger"


def test_secret_leak_scanner_allows_boolean_presence_and_source_logs(tmp_path: Path) -> None:
    source = tmp_path / "safe.py"
    source.write_text(
        """
def main(token, logger):
    print(f"token_provided={bool(token)}")
    logger.info("token_source=%s", "env")
""".strip()
        + "\n",
        encoding="utf-8",
    )

    assert scan_file(source) == []
