from __future__ import annotations

from contextvars import ContextVar
from functools import wraps
from typing import Any, Callable, Mapping

VERSION = "nico.comprehensive_final_display_metadata.v92"
_BUILDER_MARKER = "__nico_final_display_metadata_builder_v92__"
_DECISION_RENDER_MARKER = "__nico_final_display_metadata_decision_render_v92__"
_BASE_RENDER_MARKER = "__nico_final_display_metadata_base_render_v92__"
_CONTEXT: ContextVar[dict[str, str]] = ContextVar(
    "nico_final_display_metadata_v92",
    default={},
)

_DISPLAY_FIELDS = (
    "customer_name",
    "project_name",
    "primary_technical_contact",
)


def _text(value: Any, limit: int = 300) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _identity_from_call(args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> Mapping[str, Any]:
    value = kwargs.get("identity")
    if isinstance(value, Mapping):
        return value
    if args and isinstance(args[0], Mapping):
        return args[0]
    return {}


def _display_values(identity: Mapping[str, Any]) -> dict[str, str]:
    customer = _text(identity.get("customer_name") or identity.get("client_name"), 180)
    project = _text(identity.get("project_name"), 180)
    contact = _text(identity.get("primary_technical_contact"), 300)
    return {
        "customer_name": customer,
        "project_name": project,
        "primary_technical_contact": contact,
    }


def _enrich_identity_in_place(identity: Any) -> Any:
    if not isinstance(identity, dict):
        return identity
    values = _CONTEXT.get() or {}
    for field in _DISPLAY_FIELDS:
        value = _text(values.get(field), 300)
        if value and not _text(identity.get(field), 300):
            identity[field] = value
    return identity


def _wrap_builder(delegate: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    if getattr(delegate, _BUILDER_MARKER, False):
        return delegate

    @wraps(delegate)
    def wrapped(*args: Any, **kwargs: Any) -> dict[str, Any]:
        identity = _identity_from_call(args, kwargs)
        token = _CONTEXT.set(_display_values(identity))
        try:
            return delegate(*args, **kwargs)
        finally:
            _CONTEXT.reset(token)

    setattr(wrapped, _BUILDER_MARKER, True)
    setattr(wrapped, "_nico_previous", delegate)
    return wrapped


def _wrap_decision_initial_render(delegate: Callable[..., Any]) -> Callable[..., Any]:
    if getattr(delegate, _DECISION_RENDER_MARKER, False):
        return delegate

    @wraps(delegate)
    def wrapped(required_identity: dict[str, Any], *args: Any, **kwargs: Any) -> Any:
        # This is the first decision-grade render seam reached after the top-level
        # builder creates its six canonical scope fields. Mutate only that local
        # report-identity dictionary so every later render, contract and canonical
        # serialization step sees the same optional display metadata.
        _enrich_identity_in_place(required_identity)
        return delegate(required_identity, *args, **kwargs)

    setattr(wrapped, _DECISION_RENDER_MARKER, True)
    setattr(wrapped, "_nico_previous", delegate)
    return wrapped


def _wrap_base_identity_renderer(delegate: Callable[..., Any]) -> Callable[..., Any]:
    if getattr(delegate, _BASE_RENDER_MARKER, False):
        return delegate

    @wraps(delegate)
    def wrapped(identity: dict[str, Any], *args: Any, **kwargs: Any) -> Any:
        # The native/stable worker can call the base report package directly. Its
        # required identity dictionary is created inside the builder and reaches
        # _markdown before canonical serialization and PDF construction. Enriching
        # that same dictionary here keeps optional display metadata in the final
        # canonical JSON without touching canonical customer/project scope IDs.
        _enrich_identity_in_place(identity)
        return delegate(identity, *args, **kwargs)

    setattr(wrapped, _BASE_RENDER_MARKER, True)
    setattr(wrapped, "_nico_previous", delegate)
    return wrapped


def install_comprehensive_final_display_metadata_v92() -> dict[str, Any]:
    """Keep supplied display metadata through the final isolated report builder.

    Earlier fixes correctly retained client/project/contact values in durable human
    evidence and recovered them at the detached worker identity boundary. The final
    report builders then reconstructed a six-field canonical identity and silently
    dropped those optional display fields before canonical JSON and PDF generation.

    This installer repairs that exact last-loss boundary. It does not alter canonical
    customer/project scope identifiers, scoring, findings, review state, or delivery
    authority.
    """

    from nico import comprehensive_decision_grade_report_v5 as decision_report
    from nico import comprehensive_native_providers as providers
    from nico import comprehensive_report_package as base_report

    decision_report._initial_render = _wrap_decision_initial_render(
        decision_report._initial_render
    )
    base_report._markdown = _wrap_base_identity_renderer(base_report._markdown)
    base_report._pdf = _wrap_base_identity_renderer(base_report._pdf)

    decision_report.build_comprehensive_report_package = _wrap_builder(
        decision_report.build_comprehensive_report_package
    )
    providers.build_comprehensive_report_package = _wrap_builder(
        providers.build_comprehensive_report_package
    )
    base_report.build_comprehensive_report_package = _wrap_builder(
        base_report.build_comprehensive_report_package
    )

    worker_runtime_bound = False
    try:
        from nico import comprehensive_report_worker_runtime_v90 as worker_runtime

        worker_runtime.build_comprehensive_report_package = _wrap_builder(
            worker_runtime.build_comprehensive_report_package
        )
        worker_runtime_bound = bool(
            getattr(
                worker_runtime.build_comprehensive_report_package,
                _BUILDER_MARKER,
                False,
            )
        )
    except Exception:
        # Some offline report-only tests do not import the detached runtime. The
        # decision-grade and base builder bindings above remain independently valid.
        worker_runtime_bound = False

    return {
        "artifact_schema": VERSION,
        "status": "installed",
        "bound": True,
        "decision_grade_identity_enrichment_bound": bool(
            getattr(decision_report._initial_render, _DECISION_RENDER_MARKER, False)
        ),
        "base_markdown_identity_enrichment_bound": bool(
            getattr(base_report._markdown, _BASE_RENDER_MARKER, False)
        ),
        "base_pdf_identity_enrichment_bound": bool(
            getattr(base_report._pdf, _BASE_RENDER_MARKER, False)
        ),
        "decision_grade_builder_context_bound": bool(
            getattr(
                decision_report.build_comprehensive_report_package,
                _BUILDER_MARKER,
                False,
            )
        ),
        "provider_builder_context_bound": bool(
            getattr(
                providers.build_comprehensive_report_package,
                _BUILDER_MARKER,
                False,
            )
        ),
        "detached_worker_builder_context_bound": worker_runtime_bound,
        "customer_name_preserved": True,
        "project_name_preserved": True,
        "primary_technical_contact_preserved": True,
        "canonical_scope_ids_unchanged": True,
        "canonical_scores_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "_enrich_identity_in_place",
    "install_comprehensive_final_display_metadata_v92",
]
