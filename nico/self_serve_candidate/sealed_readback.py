"""Offline exact artifact readback. Not a report route or authorization policy."""
from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest
import re


@dataclass(frozen=True)
class SealedPdf:
    """A binding loaded from separately verified server-side authorization state."""

    sha256_hex: str
    size: int


def exact_pdf_bytes(retained: bytes, *, binding: SealedPdf) -> bytes:
    """Return the original stored bytes or fail; never call a report renderer."""
    if (
        not isinstance(binding.sha256_hex, str)
        or re.fullmatch(r"[a-f0-9]{64}", binding.sha256_hex) is None
        or type(binding.size) is not int
        or binding.size < 5
    ):
        raise ValueError("sealed_pdf_binding_invalid")
    if type(retained) is not bytes or len(retained) != binding.size or not retained.startswith(b"%PDF-"):
        raise ValueError("sealed_pdf_bytes_invalid")
    if not compare_digest(sha256(retained).hexdigest(), binding.sha256_hex):
        raise ValueError("sealed_pdf_digest_mismatch")
    return retained
