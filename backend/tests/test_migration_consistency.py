"""Migration baseline consistency checks (issue.md 约定 7 的唯一低层验证).

Acceptance covered (ticket 06):
    1. Building an empty database two ways — ``Base.metadata.create_all`` and
       ``alembic upgrade head`` — yields the same tables, columns, types,
       nullability, server defaults, indexes and foreign keys.
    2. The migration chain can be downgraded from head to base and upgraded back
       to head without errors, leaving no business objects behind after downgrade.
    3. ``users.id`` is an autoincrement integer on both paths and every foreign key
       referencing it has exactly the same type (no leftover UUID assumption).
    4. The revision chain is linear with a single head; one ``upgrade head`` on an
       empty database succeeds.
    5. Neither migrations nor models branch on the database dialect — SQLite
       compatibility lives only in ``app/core/compat.py``.

Type comparison: both paths are reflected from the same SQLite database, so the
reflected column types are already the compat-mapped DDL types
(``compat.JSONB`` -> ``TEXT`` on SQLite). The ORM-declared types are additionally
compiled against the target dialect and compared with what the migration created,
so the compat layer stays the single source of type mapping.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic.command import downgrade, upgrade
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine

import app.models  # noqa: F401  register every ORM model in Base.metadata
from app.core.compat import JSONB
from app.core.database import Base

BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_DIR = BACKEND_DIR / "alembic"
VERSIONS_DIR = ALEMBIC_DIR / "versions"
MODELS_DIR = BACKEND_DIR / "app" / "models"

# Alembic's own bookkeeping table; not part of the application schema.
ALEMBIC_VERSION_TABLE = "alembic_version"


def _sqlite_url(db_path: Path) -> str:
    """Turn a temp path into a SQLite URL (forward slashes on every OS)."""
    return f"sqlite:///{db_path.as_posix()}"


def _alembic_config(db_url: str) -> Config:
    """Build an Alembic config with an injected URL.

    Deliberately not reading alembic.ini: that avoids reconfiguring global logging
    via fileConfig and avoids depending on the current working directory. env.py
    only falls back to the application settings when no URL was injected.
    """
    config = Config()
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    config.set_main_option("prepend_sys_path", str(BACKEND_DIR))
    config.set_main_option("sqlalchemy.url", db_url)
    return config


def _create_orm_database(db_path: Path) -> Engine:
    """Path A: create all tables from ORM metadata (development truth)."""
    engine = create_engine(_sqlite_url(db_path))
    Base.metadata.create_all(engine)
    return engine


def _create_migrated_database(db_path: Path) -> Engine:
    """Path B: run Alembic from an empty database up to head (production truth)."""
    upgrade(_alembic_config(f"sqlite+aiosqlite:///{db_path.as_posix()}"), "head")
    return create_engine(_sqlite_url(db_path))


def _normalize_sql(value: Any) -> str | None:
    """Normalize a DDL fragment so casing and whitespace differences are not drift."""
    if value is None:
        return None
    return " ".join(str(value).upper().split())


def _schema_snapshot(engine: Engine) -> dict[str, dict[str, Any]]:
    """Reflect the whole database into a comparable snapshot."""
    inspector = inspect(engine)
    snapshot: dict[str, dict[str, Any]] = {}
    for table_name in sorted(inspector.get_table_names()):
        if table_name == ALEMBIC_VERSION_TABLE:
            continue
        snapshot[table_name] = {
            "columns": {
                column["name"]: {
                    "type": _normalize_sql(column["type"]),
                    "nullable": column["nullable"],
                    "server_default": _normalize_sql(column["default"]),
                }
                for column in inspector.get_columns(table_name)
            },
            "indexes": {
                index["name"]: {
                    "columns": tuple(index["column_names"]),
                    "unique": bool(index["unique"]),
                }
                for index in inspector.get_indexes(table_name)
            },
            "foreign_keys": sorted(
                (
                    tuple(foreign_key["constrained_columns"]),
                    foreign_key["referred_table"],
                    tuple(foreign_key["referred_columns"]),
                    _normalize_sql(foreign_key["options"].get("ondelete")) or "",
                )
                for foreign_key in inspector.get_foreign_keys(table_name)
            ),
        }
    return snapshot


def _diff_snapshots(expected: dict[str, Any], actual: dict[str, Any], path: str = "") -> list[str]:
    """Recursively compare snapshots and return readable differences (empty == equal)."""
    problems: list[str] = []
    for key in sorted({*expected, *actual}):
        location = f"{path}.{key}" if path else str(key)
        if key not in expected:
            problems.append(f"{location}: only present on the migration path")
        elif key not in actual:
            problems.append(f"{location}: only present on the ORM path")
        else:
            left, right = expected[key], actual[key]
            if isinstance(left, dict) and isinstance(right, dict):
                problems.extend(_diff_snapshots(left, right, location))
            elif left != right:
                problems.append(f"{location}: ORM={left!r} migration={right!r}")
    return problems


def _format_problems(problems: list[str]) -> str:
    return "migrations and ORM metadata disagree:\n" + "\n".join(
        f"  - {problem}" for problem in problems
    )


def test_orm_metadata_and_migrations_produce_identical_schema(tmp_path: Path) -> None:
    """Both build paths must produce exactly the same tables, columns and keys."""
    orm_engine = _create_orm_database(tmp_path / "orm-schema.db")
    migrated_engine = _create_migrated_database(tmp_path / "migrated-schema.db")
    try:
        expected = _schema_snapshot(orm_engine)
        actual = _schema_snapshot(migrated_engine)
        assert expected, "ORM metadata registers no tables; check the app.models imports"
        assert actual, "upgrade head created no business tables"
        problems = _diff_snapshots(expected, actual)
        assert not problems, _format_problems(problems)
    finally:
        orm_engine.dispose()
        migrated_engine.dispose()


def test_compat_layer_types_round_trip_through_migrations(tmp_path: Path) -> None:
    """ORM-declared types (compat-mapped per dialect) match the migrated columns."""
    migrated_engine = _create_migrated_database(tmp_path / "compat-types.db")
    dialect = migrated_engine.dialect
    inspector = inspect(migrated_engine)
    try:
        problems: list[str] = []
        for table_name, table in Base.metadata.tables.items():
            migrated_columns = {
                column["name"]: column for column in inspector.get_columns(table_name)
            }
            for column in table.columns:
                migrated = migrated_columns.get(column.name)
                if migrated is None:
                    problems.append(f"{table_name}.{column.name}: missing from the migration")
                    continue
                # A TypeDecorator (compat JSONB) expands to the real DDL type per dialect.
                expected_type = _normalize_sql(column.type.compile(dialect=dialect))
                actual_type = _normalize_sql(migrated["type"])
                if expected_type != actual_type:
                    problems.append(
                        f"{table_name}.{column.name}: ORM declares {expected_type}, "
                        f"migration created {actual_type}"
                    )
                if bool(column.nullable) != bool(migrated["nullable"]):
                    problems.append(
                        f"{table_name}.{column.name}: ORM nullable={column.nullable}, "
                        f"migration nullable={migrated['nullable']}"
                    )
        assert not problems, _format_problems(problems)
    finally:
        migrated_engine.dispose()


def test_migrations_downgrade_to_base_and_back_up(tmp_path: Path) -> None:
    """The migration must downgrade head -> base (no leftovers) and upgrade again."""
    db_path = tmp_path / "roundtrip.db"
    config = _alembic_config(f"sqlite+aiosqlite:///{db_path.as_posix()}")

    upgrade(config, "head")
    engine = create_engine(_sqlite_url(db_path))
    try:
        schema_after_upgrade = _schema_snapshot(engine)
        assert schema_after_upgrade, "upgrade head created no business tables"
    finally:
        engine.dispose()

    downgrade(config, "base")
    engine = create_engine(_sqlite_url(db_path))
    try:
        leftovers = set(inspect(engine).get_table_names()) - {ALEMBIC_VERSION_TABLE}
        assert not leftovers, f"downgrade to base left objects behind: {sorted(leftovers)}"
    finally:
        engine.dispose()

    upgrade(config, "head")
    engine = create_engine(_sqlite_url(db_path))
    try:
        assert _schema_snapshot(engine) == schema_after_upgrade, (
            "schema after downgrade+upgrade differs from the first upgrade"
        )
    finally:
        engine.dispose()


def test_users_primary_key_is_autoincrement_integer_in_both_paths(tmp_path: Path) -> None:
    """users.id is an autoincrement integer everywhere, and so is every FK to it."""
    orm_engine = _create_orm_database(tmp_path / "orm-pk.db")
    migrated_engine = _create_migrated_database(tmp_path / "migrated-pk.db")
    try:
        orm_id = Base.metadata.tables["users"].columns["id"]
        assert isinstance(orm_id.type, sa.Integer), "ORM users.id is not an integer column"

        for label, engine in (("ORM", orm_engine), ("migration", migrated_engine)):
            inspector = inspect(engine)
            assert inspector.get_pk_constraint("users")["constrained_columns"] == ["id"], label
            users_columns = {column["name"]: column for column in inspector.get_columns("users")}
            id_column = users_columns["id"]
            id_type = _normalize_sql(id_column["type"])
            assert id_type == "INTEGER", f"{label}: users.id is {id_type}, expected an integer"
            assert id_column["default"] is None, (
                f"{label}: users.id must not carry a default "
                f"(the removed gen_random_uuid() assumption)"
            )

            referencing_columns: list[tuple[str, str]] = []
            for table_name in inspector.get_table_names():
                if table_name == ALEMBIC_VERSION_TABLE:
                    continue
                columns = {column["name"]: column for column in inspector.get_columns(table_name)}
                for foreign_key in inspector.get_foreign_keys(table_name):
                    if foreign_key["referred_table"] != "users":
                        continue
                    if foreign_key["referred_columns"] != ["id"]:
                        continue
                    for local_name in foreign_key["constrained_columns"]:
                        referencing_columns.append((table_name, local_name))
                        local_type = _normalize_sql(columns[local_name]["type"])
                        assert local_type == id_type, (
                            f"{label}: {table_name}.{local_name} is {local_type} "
                            f"but users.id is {id_type}"
                        )
            assert referencing_columns, f"{label}: nothing references users.id; check is vacuous"

        # Functional proof: users.id created by the migration really autoincrements.
        with migrated_engine.begin() as connection:
            connection.execute(sa.text("INSERT INTO users (openid, is_admin) VALUES ('pk-1', 0)"))
            connection.execute(sa.text("INSERT INTO users (openid) VALUES ('pk-2')"))
            inserted_ids = [
                row[0]
                for row in connection.execute(sa.text("SELECT id FROM users ORDER BY id"))
            ]
        assert inserted_ids == [1, 2], (
            f"users.id from the migration does not autoincrement: {inserted_ids}"
        )
    finally:
        orm_engine.dispose()
        migrated_engine.dispose()


def test_alembic_revision_chain_is_linear_with_single_head() -> None:
    """The revision chain is linear: single head, single base, no merge nodes."""
    script = ScriptDirectory.from_config(_alembic_config("sqlite+aiosqlite://"))
    heads = script.get_heads()
    bases = script.get_bases()
    assert len(heads) == 1, f"multiple heads in the migration directory: {heads}"
    assert len(bases) == 1, f"multiple bases in the migration directory: {bases}"

    revisions = list(script.walk_revisions("base", "heads"))
    assert revisions, "the migration directory contains no revisions"
    assert revisions[0].revision == heads[0]
    for revision, parent in zip(revisions, revisions[1:]):
        assert not isinstance(revision.down_revision, tuple), (
            f"{revision.revision} is a merge node; the chain must be linear"
        )
        assert revision.down_revision == parent.revision, (
            f"{revision.revision}.down_revision does not continue the chain"
        )
    assert revisions[-1].down_revision is None, "the oldest revision must not have a down_revision"


# Only real dialect branching is forbidden; comments naming a database are fine.
_FORBIDDEN_DIALECT_PATTERNS = (
    "dialects.postgresql",
    "dialects.sqlite",
    "dialect.name",
    "is_sqlite",
    "create_engine(",
)


def test_migrations_and_models_have_no_dialect_branches() -> None:
    """Dialect differences belong to app/core/compat.py, never to migrations/models."""
    offenders: list[str] = []
    for path in sorted((*VERSIONS_DIR.glob("*.py"), *MODELS_DIR.glob("*.py"))):
        source = path.read_text(encoding="utf-8").lower()
        for pattern in _FORBIDDEN_DIALECT_PATTERNS:
            if pattern in source:
                offenders.append(f"{path.relative_to(BACKEND_DIR).as_posix()}: found {pattern!r}")
    assert not offenders, "dialect branching found in migrations or models:\n" + "\n".join(
        f"  - {offender}" for offender in offenders
    )


_DECLARATION = re.compile(
    r"op\.create_table\(\s*['\"](?P<table>\w+)['\"]"
    r"|op\.add_column\(\s*['\"](?P<added_table>\w+)['\"]\s*,\s*"
    r"sa\.Column\(\s*['\"](?P<added_column>\w+)['\"]\s*,\s*(?P<added_type>[A-Za-z_][\w.]*)"
    r"|sa\.Column\(\s*['\"](?P<column>\w+)['\"]\s*,\s*(?P<type>[A-Za-z_][\w.]*)",
    re.DOTALL,
)


def _declared_columns(source: str) -> dict[tuple[str, str], str]:
    """Read (table, column) -> declared type expression from the migration source.

    Supports both ``op.create_table`` blocks and later ``op.add_column`` calls, so a
    future revision that appends a JSON column is covered by the same convention.
    """
    declared: dict[tuple[str, str], str] = {}
    table_name: str | None = None
    for match in _DECLARATION.finditer(source):
        if match.group("table"):
            table_name = match.group("table")
        elif match.group("added_table"):
            declared.setdefault(
                (match.group("added_table"), match.group("added_column")),
                match.group("added_type"),
            )
        elif table_name and match.group("column"):
            declared.setdefault((table_name, match.group("column")), match.group("type"))
    return declared


def test_migration_declares_json_columns_through_compat_layer() -> None:
    """JSON columns must use the compat JSONB type, or Postgres would drift from the ORM."""
    revision_source = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(VERSIONS_DIR.glob("*.py"))
    )
    assert "from app.core.compat import JSONB" in revision_source, (
        "migrations must import JSONB from app/core/compat.py, not from sqlalchemy.dialects"
    )

    declared = _declared_columns(revision_source)
    json_columns = [
        (table.name, column.name)
        for table in Base.metadata.tables.values()
        for column in table.columns
        if isinstance(column.type, JSONB)
    ]
    assert json_columns, "the ORM has no JSON columns; check the compat import"

    problems = [
        f"{table_name}.{column_name}: migration declares "
        f"{declared.get((table_name, column_name))!r}, the ORM declares compat JSONB"
        for table_name, column_name in json_columns
        if declared.get((table_name, column_name)) != "JSONB"
    ]
    assert not problems, _format_problems(problems)
