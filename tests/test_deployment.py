import json
from pathlib import Path

import pytest

from app.db import (
    POSTGRES_SCHEMA,
    execute_query,
    executemany_query,
    insert_and_get_id,
    is_postgres_database,
)
from app.main import create_app, resolve_database_target


class FakeCursor:
    def __init__(self, row: dict | None = None) -> None:
        self.row = row

    def fetchone(self) -> dict | None:
        return self.row


class FakePostgresConnection:
    def __init__(self, returned_id: int = 42) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self.returned_id = returned_id

    def execute(self, query: str, parameters: tuple) -> FakeCursor:
        self.calls.append((query, parameters))
        return FakeCursor({"id": self.returned_id})

    def cursor(self):
        connection = self

        class BatchCursor:
            def __enter__(self):
                return self

            def __exit__(self, *_: object) -> None:
                return None

            def executemany(self, query: str, rows: list[tuple]) -> None:
                connection.calls.append((query, tuple(rows)))

        return BatchCursor()


def test_explicit_test_database_wins_over_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/splitledger")
    explicit_path = tmp_path / "test.db"
    assert resolve_database_target(explicit_path) == explicit_path


def test_database_url_is_used_for_deployment(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = "postgresql://example.invalid/splitledger"
    monkeypatch.setenv("DATABASE_URL", database_url)
    assert resolve_database_target() == database_url
    assert is_postgres_database(database_url)


def test_vercel_fails_with_actionable_error_without_persistent_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    with pytest.raises(RuntimeError, match="DATABASE_URL is required on Vercel"):
        resolve_database_target()


def test_production_requires_private_session_secret(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        create_app(tmp_path / "production-config.db", seed=False)


def test_production_rejects_example_session_secret(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SESSION_SECRET", "replace-this-with-a-long-random-development-secret")
    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        create_app(tmp_path / "production-config.db", seed=False)


def test_postgres_queries_translate_placeholders_and_return_generated_id() -> None:
    connection = FakePostgresConnection(returned_id=17)
    execute_query(connection, "SELECT id FROM users WHERE id = ?", (7,))
    generated_id = insert_and_get_id(
        connection,
        "INSERT INTO users (display_name, password_hash) VALUES (?, ?)",
        ("Asha", "hash"),
    )

    assert connection.calls[0] == ("SELECT id FROM users WHERE id = %s", (7,))
    assert connection.calls[1][0].endswith("VALUES (%s, %s) RETURNING id")
    assert generated_id == 17


def test_postgres_batch_insert_uses_cursor_and_translated_placeholders() -> None:
    connection = FakePostgresConnection()
    executemany_query(
        connection,
        "INSERT INTO expense_shares (expense_id, user_id, amount_paise) VALUES (?, ?, ?)",
        [(1, 2, 50), (1, 3, 50)],
    )

    query, rows = connection.calls[0]
    assert query.endswith("VALUES (%s, %s, %s)")
    assert rows == ((1, 2, 50), (1, 3, 50))


def test_postgres_schema_contains_all_domain_tables() -> None:
    schema = "\n".join(POSTGRES_SCHEMA)
    for table in ("users", "groups", "group_members", "expenses", "expense_shares"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in schema


def test_vercel_entrypoint_and_configuration_are_present() -> None:
    from api.index import app

    assert app.title == "SplitLedger"
    configuration = json.loads(Path("vercel.json").read_text(encoding="utf-8"))
    assert configuration["builds"][0]["src"] == "api/index.py"
    assert configuration["routes"][0]["dest"] == "api/index.py"


def test_example_environment_never_contains_credentials() -> None:
    values = {}
    for line in Path(".env.example").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", maxsplit=1)
            values[key] = value

    assert values["GEMINI_API_KEY"] == ""
    assert values["DATABASE_URL"] == ""
    assert values["PARSER_MODE"] == "mock"
