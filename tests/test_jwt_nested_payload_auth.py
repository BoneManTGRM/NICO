"""Regression for CVE-2026-101918 in the pinned JWT dependency."""
import base64

import jwt
import pytest


def test_deeply_nested_payload_raises_documented_decode_error():
    def segment(value):
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    # Exceeds the JSON decoder depth on both Python 3.11 and Python 3.12.
    token = ".".join([
        segment(b'{"alg":"RS256","kid":"invalid"}'),
        segment(b'{"nested":' + b"[" * 11000 + b"0" + b"]" * 11000 + b"}"),
        segment(b"invalid-signature"),
    ])
    with pytest.raises(jwt.DecodeError):
        jwt.decode(token, options={"verify_signature": False})
