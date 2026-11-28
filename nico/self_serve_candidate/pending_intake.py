"""Minimum form state carried by a single server-side sign-in attempt."""
from dataclasses import dataclass, field, replace
import json
import re
from unicodedata import category

_REPOSITORY = re.compile(
    r"(?:https://github\.com/)?[A-Za-z0-9-]{1,39}/[A-Za-z0-9_.-]{1,100}/?"
)
_TERMS = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")


@dataclass(frozen=True)
class PendingIntake:
    repository: str = field(repr=False)
    full_name: str = field(repr=False)
    permission_attested: bool
    terms_shown: str
    locale: str = "en"

    def __post_init__(self):
        if (
            type(self.repository) is not str
            or not _REPOSITORY.fullmatch(self.repository)
            or self.repository.rstrip("/").rsplit("/", 1)[1] in {".", ".."}
            or type(self.full_name) is not str
            or not self.full_name.strip()
            or len(self.full_name) > 200
            or any(category(char) in {"Cc", "Cs"} for char in self.full_name)
            or type(self.permission_attested) is not bool
            or type(self.terms_shown) is not str
            or not _TERMS.fullmatch(self.terms_shown)
            or type(self.locale) is not str
            or self.locale not in ("en", "es-MX")
        ):
            raise ValueError("invalid pending intake")

    @property
    def assessment_path(self) -> str:
        return "/es/assessment" if self.locale == "es-MX" else "/assessment"

    def with_current_terms(self, current_terms: str) -> "PendingIntake":
        """Keep the fields, but never carry consent onto different terms."""
        if type(current_terms) is not str or not _TERMS.fullmatch(current_terms):
            raise ValueError("invalid current terms")
        if self.terms_shown != current_terms:
            return replace(self, permission_attested=False)
        return self


def encode_pending(value: PendingIntake | None) -> str | None:
    if value is None:
        return None
    if type(value) is not PendingIntake:
        raise ValueError("invalid pending intake")
    return json.dumps([value.repository, value.full_name, value.permission_attested,
                       value.terms_shown, value.locale], ensure_ascii=False, separators=(",", ":"))


def decode_pending(value: str | None) -> PendingIntake | None:
    if value is None:
        return None
    if type(value) is not str or len(value) > 800:
        raise ValueError("invalid pending intake")
    try:
        fields = json.loads(value)
    except ValueError:
        raise ValueError("invalid pending intake") from None
    if type(fields) is not list or len(fields) not in (4, 5):
        raise ValueError("invalid pending intake")
    return PendingIntake(*fields)
