from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "supabase" / "migrations"


def test_migration_filenames_match_applied_remote_history_versions():
    expected = {
        "20261024180631": "20261023000000_council_conversations",
        "20261024180641": "20261024134656_restrict_rls_auto_enable_execute",
    }
    filenames = {path.name for path in MIGRATIONS.glob("*.sql")}
    for version, name in expected.items():
        assert f"{version}_{name}.sql" in filenames
