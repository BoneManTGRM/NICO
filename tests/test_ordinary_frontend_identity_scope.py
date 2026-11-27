from copy import deepcopy

from nico.comprehensive_release_provenance_v1 import _presentation_localizer, _provenance_lines


def case(status="mismatch"):
    return dict(frontend_identity_source="configured_release_label", frontend_build_commit="a"*40,
                frontend_runtime_observation={"frontend_observation_schema":"v1", "status":status,
                "release_sha":"b"*40,"deployment_id":"observed-id"},
                backend_build_commit="b"*40, frontend_observed_source_revision="b"*40,
                frontend_deployment_id="configured-id", frontend_backend_source_alignment="unverified",
                release_identity_scope="report_generation_runtime; assessed repository identity is separate",
                scanner_execution_evidence={})


def test_configured_discrepancy_does_not_establish_deployed_mismatch():
    record=case()
    before=deepcopy(record)
    lines=dict(_provenance_lines(record))
    assert lines["Frontend configured-identity match"]=="mismatch"
    assert lines["Frontend/backend observed source alignment"]=="unverified"
    assert lines["Report-generation runtime identity readiness"]=="unverified"
    assert lines["Configured frontend deployment ID"]=="configured-id"
    assert lines["Observed frontend deployment identity"]=="observed-id"
    assert "alone does not establish" in lines["Frontend identity interpretation"]
    assert record==before


def test_matching_and_missing_observations_do_not_acquire_conflict():
    for record in [case("match"), {}, {"frontend_runtime_observation":{"status":"mismatch"}}]:
        assert "Frontend identity interpretation" not in dict(_provenance_lines(record))


def test_scope_explanation_is_localized_for_spanish():
    localize=_presentation_localizer(lambda s: "Procedencia de NICO" if s=="NICO Release Provenance" else s)
    lines={localize(k):localize(v) for k,v in _provenance_lines(case(),spanish=True)}
    assert "por sí sola no demuestra" in lines["Interpretación de la identidad del frontend"]
    assert lines["Identificador configurado del despliegue del frontend"]=="configured-id"
