from nico.full_report_download_response_v1 import attach_download_responses, build_download_response


def _delivery(fmt: str = "pdf") -> dict:
    return {
        "assessment_id": "assessment-1",
        "format": fmt,
        "client_delivery_allowed": True,
        "artifact": {
            "artifact_id": f"artifact-{fmt}",
            "filename": f"nico-full-assessment-1.{ 'md' if fmt == 'markdown' else fmt }",
            "content_type": {
                "pdf": "application/pdf",
                "html": "text/html; charset=utf-8",
                "markdown": "text/markdown; charset=utf-8",
            }[fmt],
            "byte_length": 4096,
            "sha256": "a" * 64,
        },
    }


def test_ready_response_contains_mobile_safe_headers() -> None:
    response = build_download_response(
        _delivery("pdf"),
        requested_assessment_id="assessment-1",
        requested_format="pdf",
    )
    assert response["status"] == "ready"
    assert response["client_delivery_allowed"] is True
    assert response["required_headers_present"] is True
    assert response["range_requests_supported"] is True
    assert response["headers"]["Content-Type"] == "application/pdf"
    assert response["headers"]["Content-Length"] == "4096"
    assert response["headers"]["Accept-Ranges"] == "bytes"
    assert response["headers"]["Cache-Control"] == "private, no-store, max-age=0"
    assert response["headers"]["ETag"].startswith('"sha256:')


def test_response_fails_closed_for_wrong_assessment() -> None:
    response = build_download_response(
        _delivery("pdf"),
        requested_assessment_id="assessment-2",
        requested_format="pdf",
    )
    assert response["status"] == "blocked"
    assert response["headers"] == {}
    assert "assessment_identity_mismatch" in response["issues"]


def test_response_fails_closed_for_wrong_format() -> None:
    response = build_download_response(
        _delivery("pdf"),
        requested_assessment_id="assessment-1",
        requested_format="html",
    )
    assert response["client_delivery_allowed"] is False
    assert "format_mismatch" in response["issues"]


def test_response_rejects_unsafe_filename() -> None:
    delivery = _delivery("pdf")
    delivery["artifact"]["filename"] = "../report.pdf"
    response = build_download_response(
        delivery,
        requested_assessment_id="assessment-1",
        requested_format="pdf",
    )
    assert response["client_delivery_allowed"] is False
    assert "unsafe_filename" in response["issues"]


def test_response_requires_positive_length_and_checksum() -> None:
    delivery = _delivery("pdf")
    delivery["artifact"]["byte_length"] = 0
    delivery["artifact"]["sha256"] = ""
    response = build_download_response(
        delivery,
        requested_assessment_id="assessment-1",
        requested_format="pdf",
    )
    assert response["client_delivery_allowed"] is False
    assert "missing_byte_length" in response["issues"]
    assert "invalid_byte_length" in response["issues"]
    assert "missing_sha256" in response["issues"]


def test_attach_download_responses_requires_all_formats() -> None:
    result = {
        "client_delivery_allowed": True,
        "full_delivery_contract": {
            "formats": {
                "pdf": _delivery("pdf"),
                "html": _delivery("html"),
                "markdown": _delivery("markdown"),
            }
        },
    }
    attach_download_responses(result, assessment_id="assessment-1")
    assert result["full_download_responses"]["all_formats_ready"] is True
    assert result["client_delivery_allowed"] is True


def test_attach_download_responses_preserves_existing_block() -> None:
    result = {
        "client_delivery_allowed": False,
        "full_delivery_contract": {
            "formats": {
                "pdf": _delivery("pdf"),
                "html": _delivery("html"),
                "markdown": _delivery("markdown"),
            }
        },
    }
    attach_download_responses(result, assessment_id="assessment-1")
    assert result["full_download_responses"]["all_formats_ready"] is True
    assert result["client_delivery_allowed"] is False
