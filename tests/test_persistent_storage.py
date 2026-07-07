from nico import storage as storage_module


class DurableFakePostgresAdapter:
    tables = {}

    def __init__(self, database_url):
        self.database_url = database_url

    def status(self):
        return {
            "mode": "postgres",
            "adapter": "postgres",
            "database_url_configured": True,
            "persistence_available": True,
            "persistence_note": "fake durable postgres active",
            "schema_available": True,
            "adapter_contract_available": True,
            "migration_endpoint_available": True,
        }

    def schema(self):
        return storage_module.POSTGRES_SCHEMA

    def put(self, table, item_id, payload):
        self.tables.setdefault(table, {})[item_id] = dict(payload, id=item_id)
        return dict(self.tables[table][item_id])

    def get(self, table, item_id):
        item = self.tables.get(table, {}).get(item_id)
        return dict(item) if item else None

    def list(self, table, customer_id=None, project_id=None):
        items = list(self.tables.get(table, {}).values())
        if customer_id:
            items = [item for item in items if item.get("customer_id") == customer_id]
        if project_id:
            items = [item for item in items if item.get("project_id") == project_id]
        return [dict(item) for item in items]


class BrokenPostgresAdapter:
    def __init__(self, database_url):
        raise RuntimeError("cannot connect")


def test_storage_uses_memory_without_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    store = storage_module.Storage()

    status = store.status()

    assert status["adapter"] == "memory"
    assert status["persistence_available"] is False
    assert "durability_warning" in status


def test_storage_uses_postgres_when_database_url_and_adapter_available(monkeypatch):
    DurableFakePostgresAdapter.tables = {}
    monkeypatch.setenv("DATABASE_URL", "postgresql://nico:test@example/nico")
    monkeypatch.setattr(storage_module, "PostgresAdapter", DurableFakePostgresAdapter)

    first = storage_module.Storage()
    first.put("assessment_runs", "run_1", {"customer_id": "cust", "project_id": "proj", "status": "complete"})
    second = storage_module.Storage()

    assert first.status()["persistence_available"] is True
    assert second.status()["adapter"] == "postgres"
    assert second.get("assessment_runs", "run_1")["status"] == "complete"


def test_storage_falls_back_when_postgres_startup_fails(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://nico:test@example/nico")
    monkeypatch.setattr(storage_module, "PostgresAdapter", BrokenPostgresAdapter)

    store = storage_module.Storage()
    status = store.status()

    assert status["adapter"] == "memory"
    assert status["persistence_available"] is False
    assert "adapter_error" in status
    assert "durability_warning" in status


def test_storage_can_disable_postgres_explicitly(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://nico:test@example/nico")
    monkeypatch.setenv("NICO_DISABLE_POSTGRES", "true")
    monkeypatch.setattr(storage_module, "PostgresAdapter", DurableFakePostgresAdapter)

    store = storage_module.Storage()
    status = store.status()

    assert status["adapter"] == "memory"
    assert status["postgres_disabled"] is True
    assert status["persistence_available"] is False
