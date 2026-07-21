from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any, Callable

from nico.provider_neutral_contract import ProviderKind, normalize_provider


class CredentialRotationError(RuntimeError):
    pass


@dataclass(frozen=True)
class CredentialRotationPolicy:
    max_age_days: int = 90
    minimum_overlap_minutes: int = 15
    maximum_overlap_hours: int = 24
    require_dual_control: bool = True

    def validate(self) -> None:
        if self.max_age_days < 1 or self.max_age_days > 365:
            raise CredentialRotationError("credential_rotation_max_age_invalid")
        if self.minimum_overlap_minutes < 0:
            raise CredentialRotationError("credential_rotation_minimum_overlap_invalid")
        if self.maximum_overlap_hours < 1:
            raise CredentialRotationError("credential_rotation_maximum_overlap_invalid")
        if self.minimum_overlap_minutes > self.maximum_overlap_hours * 60:
            raise CredentialRotationError("credential_rotation_overlap_window_invalid")


@dataclass(frozen=True)
class CredentialVersion:
    provider: ProviderKind
    key_id: str
    version: str
    secret_reference: str
    activated_at: str
    expires_at: str
    activated_by: str
    approved_by: str
    status: str
    predecessor_version: str = ""
    retired_at: str = ""
    retired_by: str = ""
    record_sha256: str = ""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse(value: str, code: str) -> datetime:
    token = str(value or "").strip()
    if token.endswith("Z"):
        token = token[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(token)
    except ValueError as exc:
        raise CredentialRotationError(code) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _required(value: Any, code: str) -> str:
    token = " ".join(str(value or "").split())
    if not token:
        raise CredentialRotationError(code)
    return token


def _record_digest(parts: tuple[str, ...]) -> str:
    return f"sha256:{sha256('|'.join(parts).encode('utf-8')).hexdigest()}"


class CredentialRotationLedger:
    """Persists credential reference metadata only; raw secret values are never accepted."""

    def __init__(self, connection_factory: Callable[[], Any], *, dialect: str = "sqlite") -> None:
        if dialect not in {"sqlite", "postgres"}:
            raise ValueError("credential_rotation_dialect_unsupported")
        self._connection_factory = connection_factory
        self.dialect = dialect

    @property
    def _placeholder(self) -> str:
        return "?" if self.dialect == "sqlite" else "%s"

    def ensure_schema(self) -> None:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS nico_provider_credential_versions (
                    provider TEXT NOT NULL,
                    key_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    secret_reference TEXT NOT NULL,
                    activated_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    activated_by TEXT NOT NULL,
                    approved_by TEXT NOT NULL,
                    status TEXT NOT NULL,
                    predecessor_version TEXT NOT NULL,
                    retired_at TEXT NOT NULL,
                    retired_by TEXT NOT NULL,
                    record_sha256 TEXT NOT NULL,
                    PRIMARY KEY (provider, key_id, version)
                )
                """
            )
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _row(row: Any) -> CredentialVersion:
        return CredentialVersion(
            provider=normalize_provider(row[0]),
            key_id=str(row[1]),
            version=str(row[2]),
            secret_reference=str(row[3]),
            activated_at=str(row[4]),
            expires_at=str(row[5]),
            activated_by=str(row[6]),
            approved_by=str(row[7]),
            status=str(row[8]),
            predecessor_version=str(row[9]),
            retired_at=str(row[10]),
            retired_by=str(row[11]),
            record_sha256=str(row[12]),
        )

    def list_versions(self, provider: ProviderKind | str, key_id: str) -> tuple[CredentialVersion, ...]:
        kind = provider if isinstance(provider, ProviderKind) else normalize_provider(provider)
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT provider, key_id, version, secret_reference, activated_at, expires_at,
                       activated_by, approved_by, status, predecessor_version,
                       retired_at, retired_by, record_sha256
                FROM nico_provider_credential_versions
                WHERE provider = {self._placeholder} AND key_id = {self._placeholder}
                ORDER BY activated_at DESC
                """,
                (kind.value, key_id),
            )
            rows = cursor.fetchall()
        finally:
            connection.close()
        return tuple(self._row(row) for row in rows)

    def active(self, provider: ProviderKind | str, key_id: str, *, now: datetime | None = None) -> CredentialVersion | None:
        current = now or _utc_now()
        for record in self.list_versions(provider, key_id):
            if record.status != "active":
                continue
            if _parse(record.activated_at, "credential_activation_time_invalid") <= current < _parse(
                record.expires_at,
                "credential_expiry_time_invalid",
            ):
                return record
        return None

    def activate(
        self,
        *,
        provider: ProviderKind | str,
        key_id: str,
        version: str,
        secret_reference: str,
        activated_by: str,
        approved_by: str,
        policy: CredentialRotationPolicy,
        activated_at: str = "",
        expires_at: str = "",
    ) -> CredentialVersion:
        policy.validate()
        kind = provider if isinstance(provider, ProviderKind) else normalize_provider(provider)
        key = _required(key_id, "credential_key_id_required")
        version_token = _required(version, "credential_version_required")
        reference = _required(secret_reference, "credential_secret_reference_required")
        if not reference.replace("_", "").isalnum():
            raise CredentialRotationError("credential_secret_reference_invalid")
        actor = _required(activated_by, "credential_activator_required")
        approver = _required(approved_by, "credential_approver_required")
        if policy.require_dual_control and actor == approver:
            raise CredentialRotationError("credential_rotation_dual_control_required")
        start = _parse(activated_at, "credential_activation_time_invalid") if activated_at else _utc_now()
        end = _parse(expires_at, "credential_expiry_time_invalid") if expires_at else start + timedelta(days=policy.max_age_days)
        if end <= start:
            raise CredentialRotationError("credential_expiry_must_follow_activation")
        if end - start > timedelta(days=policy.max_age_days):
            raise CredentialRotationError("credential_rotation_max_age_exceeded")
        predecessor = self.active(kind, key, now=start)
        predecessor_version = predecessor.version if predecessor is not None else ""
        digest = _record_digest(
            (
                kind.value,
                key,
                version_token,
                reference,
                _iso(start),
                _iso(end),
                actor,
                approver,
                predecessor_version,
            )
        )
        record = CredentialVersion(
            provider=kind,
            key_id=key,
            version=version_token,
            secret_reference=reference,
            activated_at=_iso(start),
            expires_at=_iso(end),
            activated_by=actor,
            approved_by=approver,
            status="active",
            predecessor_version=predecessor_version,
            record_sha256=digest,
        )
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            values = (
                kind.value,
                key,
                version_token,
                reference,
                record.activated_at,
                record.expires_at,
                actor,
                approver,
                "active",
                predecessor_version,
                "",
                "",
                digest,
            )
            placeholders = ",".join([self._placeholder] * len(values))
            try:
                cursor.execute(
                    f"""
                    INSERT INTO nico_provider_credential_versions (
                        provider, key_id, version, secret_reference, activated_at, expires_at,
                        activated_by, approved_by, status, predecessor_version,
                        retired_at, retired_by, record_sha256
                    ) VALUES ({placeholders})
                    """,
                    values,
                )
            except Exception as exc:
                connection.rollback()
                raise CredentialRotationError("credential_version_already_exists") from exc
            connection.commit()
        finally:
            connection.close()
        return record

    def retire(
        self,
        *,
        provider: ProviderKind | str,
        key_id: str,
        version: str,
        retired_by: str,
        retired_at: str = "",
    ) -> CredentialVersion:
        kind = provider if isinstance(provider, ProviderKind) else normalize_provider(provider)
        timestamp = _parse(retired_at, "credential_retirement_time_invalid") if retired_at else _utc_now()
        actor = _required(retired_by, "credential_retirement_actor_required")
        records = {item.version: item for item in self.list_versions(kind, key_id)}
        record = records.get(version)
        if record is None:
            raise CredentialRotationError("credential_version_not_found")
        if record.status != "active":
            raise CredentialRotationError("credential_version_not_active")
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                UPDATE nico_provider_credential_versions
                SET status = {self._placeholder}, retired_at = {self._placeholder}, retired_by = {self._placeholder}
                WHERE provider = {self._placeholder} AND key_id = {self._placeholder}
                  AND version = {self._placeholder} AND status = {self._placeholder}
                """,
                ("retired", _iso(timestamp), actor, kind.value, key_id, version, "active"),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                raise CredentialRotationError("credential_retirement_conflict")
            connection.commit()
        finally:
            connection.close()
        return CredentialVersion(
            **{
                **record.__dict__,
                "status": "retired",
                "retired_at": _iso(timestamp),
                "retired_by": actor,
            }
        )


def rotation_due(
    record: CredentialVersion,
    *,
    policy: CredentialRotationPolicy,
    now: datetime | None = None,
) -> bool:
    policy.validate()
    current = now or _utc_now()
    expires = _parse(record.expires_at, "credential_expiry_time_invalid")
    return current >= expires - timedelta(hours=policy.maximum_overlap_hours)


__all__ = [
    "CredentialRotationError",
    "CredentialRotationLedger",
    "CredentialRotationPolicy",
    "CredentialVersion",
    "rotation_due",
]
