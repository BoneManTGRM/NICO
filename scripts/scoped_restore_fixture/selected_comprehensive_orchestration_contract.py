"""Static source-pinned selected definitions; checked by verifier before import."""
import json
import hashlib
from typing import Any
from collections.abc import Mapping
from nico.report_delivery_timing_v1 import report_delivery_phase
EXPRESS_STAGES = ('authorization_and_scope', 'immutable_repository_snapshot', 'repository_and_delivery_evidence', 'dependency_security_static_analysis', 'ci_cd_architecture_complexity_velocity', 'evidence_reconciliation_and_scoring', 'decision_report_generation')
COMPREHENSIVE_ONLY_STAGES = ('deep_scanner_triage', 'functional_qa', 'platform_parity', 'deployment_and_infrastructure', 'architecture_and_data_flow', 'developer_delivery_process', 'stakeholder_and_business_alignment', 'requirements_traceability', 'historical_trends_and_change_failure', 'six_month_roadmap', 'staffing_sequencing_and_cost', 'risk_reduction_and_executive_briefing', 'final_comprehensive_report_generation')
TERMINAL_STAGES = ('cross_format_truth_verification', 'human_review_request', 'client_acceptance_pending')
COMPREHENSIVE_STAGES = EXPRESS_STAGES + COMPREHENSIVE_ONLY_STAGES + TERMINAL_STAGES
