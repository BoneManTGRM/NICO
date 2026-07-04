    def payloads(self, table: str) -> list[dict]:
        return [json.loads(row["payload"]) for row in self.rows(table) if row.get("payload")]