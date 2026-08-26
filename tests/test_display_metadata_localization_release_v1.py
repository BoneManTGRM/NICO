from __future__ import annotations


def test_new_display_metadata_labels_are_localized_without_touching_user_values() -> None:
    from nico import comprehensive_current_report_truth_parity_v1 as current_truth
    from nico import comprehensive_spanish_canonical_report_v87 as canonical
    from nico.comprehensive_display_metadata_localization_v1 import (
        install_display_metadata_localization_v1,
    )
    from nico.comprehensive_spanish_current_copy_worker_v98 import (
        localize_current_report_copy_v98,
    )

    state = install_display_metadata_localization_v1()
    assert state["status"] in {"installed", "already_installed"}
    assert state["canonical_replacement_registry_bound"] is True
    assert state["current_report_dynamic_registry_bound"] is True
    assert state["runtime_cache_order_safe"] is True
    assert state["canonical_truth_mutated"] is False
    assert state["user_values_translated"] is False

    expected = {
        "Client display name": "Nombre visible del cliente",
        "Project display name": "Nombre visible del proyecto",
        "Primary technical contact": "Contacto técnico principal",
    }
    assert tuple(canonical._PRESENTATION_REPLACEMENTS[:3]) == tuple(expected.items())

    for english, spanish in expected.items():
        assert current_truth._ES_PHRASES[english] == spanish
        # Direct v87 path.
        translated = canonical._translate_presentation(english)
        assert translated == spanish
        assert english not in translated
        # v98 is the dynamic wrapper captured by the renderer cache. It must see the
        # same labels even though the wrapper itself may have been installed earlier.
        dynamic = localize_current_report_copy_v98(english)
        assert dynamic == spanish
        assert english not in dynamic

    # User-supplied metadata is concatenated only after the renderer-owned label has
    # been localized. The value therefore remains byte-for-byte identical.
    canary = "NICO Metadata Proof Contact / Cliente ACME 2026"
    direct = f"{canonical._translate_presentation('Primary technical contact')}: {canary}"
    dynamic = f"{localize_current_report_copy_v98('Primary technical contact')}: {canary}"
    assert direct == f"Contacto técnico principal: {canary}"
    assert dynamic == f"Contacto técnico principal: {canary}"


def test_final_worker_binds_metadata_localization_before_final_navigation() -> None:
    from nico.comprehensive_final_worker_pdf_reflow_v1 import (
        install_comprehensive_final_worker_pdf_reflow_v1,
    )

    state = install_comprehensive_final_worker_pdf_reflow_v1()
    assert state["bound"] is True
    assert state["display_metadata_preservation_is_stable_source"] is True
    assert state["display_metadata_es_mx_labels_bound"] is True
    assert state["canonical_truth_mutated"] is False
    assert state["human_review_required"] is True
    assert state["client_delivery_allowed"] is False
