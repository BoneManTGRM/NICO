from __future__ import annotations

from typing import Any


VERSION = "nico.comprehensive-report-semantic-manifest.v1.2"


def _section(
    section_id: str,
    title_en: str,
    title_es: str,
    purpose: str,
    *,
    toc: bool = True,
    review_package: bool = True,
    required: bool = True,
    artifact_owner: str = "comprehensive_report",
) -> dict[str, Any]:
    return {
        "section_id": section_id,
        "title_en": title_en,
        "title_es": title_es,
        "purpose": purpose,
        "inclusion_criteria": "canonical_comprehensive" if required else "when_applicable",
        "client_visible": True,
        "toc_participation": toc,
        "review_package_participation": review_package,
        "required": required,
        "artifact_owner": artifact_owner,
    }


# One ordered semantic inventory owns both locale projections. Physical pagination may
# differ by locale; logical section identity and order may not. Existing English titles
# are retained unless a canonical structural defect requires changing both projections.
REPORT_SECTION_MANIFEST: tuple[dict[str, Any], ...] = (
    _section("comprehensive_technical_assessment", "Comprehensive Technical Assessment", "Evaluación Técnica Integral", "Assessment identity and canonical scope."),
    _section("executive_decision_brief", "Executive Decision Brief", "Resumen ejecutivo para decisiones", "Decision-grade summary of material assessment truth."),
    _section("priority_constraints_and_decision_risks", "Priority Constraints and Decision Risks", "Restricciones prioritarias y riesgos de decisión", "Priority constraints, blockers, and decision risks."),
    _section("canonical_technical_scorecard", "Canonical Technical Scorecard", "Cuadro de puntuación técnica", "Canonical technical and evidence-adjusted score presentation."),
    _section("code_audit", "Code Audit", "Auditoría de código", "Exact-commit code audit evidence and conclusions."),
    _section("dependency_library_ecosystem", "Dependency / Library Ecosystem", "Ecosistema de dependencias y bibliotecas", "Dependency and library ecosystem evidence."),
    _section("secrets_exposure_review", "Secrets Exposure Review", "Revisión de exposición de secretos", "Secrets exposure evidence and limitations."),
    _section("static_analysis", "Static Analysis", "Análisis estático", "Static-analysis evidence and findings."),
    _section("ci_cd_analysis", "CI/CD Analysis", "Análisis de CI/CD", "CI/CD configuration and evidence-bound analysis."),
    _section("architecture_technical_debt", "Architecture & Technical Debt", "Arquitectura y deuda técnica", "Architecture quality and technical-debt evidence."),
    _section("velocity_complexity", "Velocity / Complexity", "Velocidad y complejidad", "Complexity and sustainable delivery context."),
    _section("repository_delivery_evidence", "Repository and Delivery Evidence", "Evidencia del repositorio y de entrega", "Repository, workflow, and delivery evidence."),
    _section("evidence_reconciliation_scoring", "Evidence Reconciliation and Scoring", "Conciliación y puntuación de evidencia", "Reconcile evidence states with canonical scoring truth."),
    _section("executive_risk_register_decision_briefing", "Executive Risk Register and Decision Briefing", "Registro ejecutivo de riesgos y resumen para decisiones", "Executive risk register and decision briefing."),
    _section("authorization_scope", "Authorization and Scope", "Autorización y alcance", "Authorization boundary and assessed scope."),
    _section("architecture_data_flow", "Architecture and Data Flow", "Arquitectura y flujo de datos", "Architecture and data-flow review companion."),
    _section("developer_delivery_process", "Developer Delivery Process", "Proceso de entrega de desarrollo", "Developer delivery process evidence and review questions."),
    _section("dependency_security_static_analysis", "Dependency, Security, and Static Analysis", "Dependencias, seguridad y análisis estático", "Combined scanner execution and triage evidence."),
    _section("ci_cd_architecture_complexity_velocity", "CI/CD, Architecture, Complexity, and Velocity", "CI/CD, arquitectura, complejidad y velocidad", "Cross-cutting CI/CD, architecture, complexity, and velocity evidence."),
    _section("review_required_candidate_register", "Review-Required Candidate Register", "Registro de candidatos que requieren revisión", "Canonical review-required candidate population."),
    _section("ci_cd_operational_readiness_historical_health", "CI/CD Operational Readiness and Historical Health", "Preparación operativa y salud histórica de CI/CD", "Operational CI/CD readiness and unscored historical context."),
    _section("functional_qa", "Functional QA", "QA funcional", "Functional QA evidence and human-review boundary."),
    _section("platform_parity", "Platform Parity", "Paridad de plataformas", "Platform and device parity evidence."),
    _section("historical_trends_change_failure", "Historical Trends and Change Failure", "Tendencias históricas y fallos de cambio", "Historical outcome context without score inflation."),
    _section("requirements_traceability", "Requirements Traceability", "Trazabilidad de requisitos", "Requirements and acceptance-traceability evidence."),
    _section("stakeholder_business_alignment", "Stakeholder and Business Alignment", "Alineación comercial y de partes interesadas", "Stakeholder authority and business-context evidence."),
    _section("risk_reduction_executive_briefing", "Risk Reduction and Executive Briefing", "Reducción de riesgo y resumen ejecutivo", "Risk-reduction decisions and executive briefing."),
    _section("six_month_roadmap", "Six-Month Roadmap", "Hoja de ruta de seis meses", "Evidence-bound roadmap guidance pending stakeholder authority."),
    _section("staffing_sequencing_cost", "Staffing, Sequencing, and Cost", "Personal, secuencia y costo", "Role, sequencing, and cost context without invented commitments."),
    _section("compact_finding_remediation_register", "Compact Finding and Remediation Register", "Registro compacto de hallazgos y remediación", "Compact material finding and remediation register."),
    _section(
        "compact_finding_remediation_register_continuation",
        "Compact Finding and Remediation Register · continuation",
        "Registro compacto de hallazgos y remediación · continuación",
        "Localized continuation title for the compact finding and remediation register.",
        toc=False,
        review_package=False,
        required=False,
    ),
    _section("complete_exact_source_index", "Complete Exact-Source Index", "Índice completo de fuentes exactas", "Exact-source identity index for retained findings."),
    _section("client_evidence_summary", "Client Evidence Summary", "Resumen de evidencia del cliente", "Client-supplied evidence and remaining gaps."),
    _section("human_review_acceptance_gate", "Human Review and Acceptance Gate", "Puerta de revisión humana y aceptación", "Explicit human-review and acceptance boundary."),
    _section("client_artifact_manifest", "Client Artifact Manifest", "Manifiesto de artefactos del cliente", "Artifact identities and integrity relationships.", artifact_owner="artifact_manifest"),
    _section("human_review_exact_artifact_approval", "Human Review and Exact-Artifact Approval Record", "Registro de revisión humana y aprobación de artefactos exactos", "Exact-artifact human approval record.", artifact_owner="approval_record"),
    _section("decision_boundary", "Decision Boundary", "Límite de decisión", "Decision boundary heading.", toc=False),
    _section("evidence_foundation", "Evidence Foundation", "Fundamento de evidencia", "Evidence foundation grouping heading.", toc=False),
    _section("deep_technical_diligence", "Deep Technical Diligence", "Diligencia técnica profunda", "Technical diligence grouping heading.", toc=False),
    _section("business_delivery_context", "Business and Delivery Context", "Contexto comercial y de entrega", "Business and delivery grouping heading.", toc=False),
    _section("roadmap_resourcing_decision", "Roadmap, Resourcing, and Decision", "Hoja de ruta, recursos y decisión", "Roadmap and resourcing grouping heading.", toc=False),
    _section("integrity_acceptance", "Integrity and Acceptance", "Integridad y aceptación", "Integrity and acceptance grouping heading.", toc=False),
)


CANONICAL_TOC_SECTIONS = tuple(
    section for section in REPORT_SECTION_MANIFEST if section["toc_participation"]
)
CANONICAL_TOC_SECTION_IDS = tuple(section["section_id"] for section in CANONICAL_TOC_SECTIONS)
CANONICAL_TOC_TITLES = tuple(section["title_en"] for section in CANONICAL_TOC_SECTIONS)
SECTION_TITLE_ES_BY_EN = {
    section["title_en"]: section["title_es"] for section in REPORT_SECTION_MANIFEST
}
SECTION_BY_ID = {section["section_id"]: section for section in REPORT_SECTION_MANIFEST}


def assert_manifest_integrity() -> None:
    ids = [section["section_id"] for section in REPORT_SECTION_MANIFEST]
    titles = [section["title_en"] for section in REPORT_SECTION_MANIFEST]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate canonical report section id")
    if len(titles) != len(set(titles)):
        raise ValueError("duplicate canonical report English title")
    required_fields = {
        "section_id",
        "title_en",
        "title_es",
        "purpose",
        "inclusion_criteria",
        "client_visible",
        "toc_participation",
        "review_package_participation",
        "required",
        "artifact_owner",
    }
    for section in REPORT_SECTION_MANIFEST:
        missing = required_fields - set(section)
        if missing:
            raise ValueError(
                f"canonical report section {section.get('section_id')} missing fields: {sorted(missing)}"
            )
        if not str(section["title_es"]).strip():
            raise ValueError(f"canonical report section {section['section_id']} missing es-MX title")


assert_manifest_integrity()


__all__ = [
    "CANONICAL_TOC_SECTION_IDS",
    "CANONICAL_TOC_SECTIONS",
    "CANONICAL_TOC_TITLES",
    "REPORT_SECTION_MANIFEST",
    "SECTION_BY_ID",
    "SECTION_TITLE_ES_BY_EN",
    "VERSION",
    "assert_manifest_integrity",
]
