"""Parse bounded native Cppcheck XML without trusting tool-supplied findings."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET


class NativeOutputRedactionRequired(ValueError):
    """Decoded native content is unsafe to retain as a redacted artifact."""



def parse_native(native_xml: str, progress: str, targets: list[str], *, version: str | None = None,
                 source_prefix: str = ''):
    if "<!DOCTYPE" in native_xml or "<!ENTITY" in native_xml:
        raise ValueError("cppcheck_xml_external_content_rejected")
    document = ET.fromstring(native_xml)
    from nico.scanner_tool_runners import redact_text
    for node in document.iter():
        values = [node.tag, node.text or "", node.tail or "", *node.attrib.keys(), *node.attrib.values()]
        if any(redact_text(value) != value for value in values):
            raise NativeOutputRedactionRequired("cppcheck_native_redaction_required")
    tool = document.find("cppcheck")
    if (document.tag != "results" or document.get("version") != "2"
            or document.find("errors") is None or tool is None
            or (version is not None and tool.get("version") != version)):
        raise ValueError("cppcheck_output_schema_invalid")
    findings, limitations = [], []
    members = set(targets)
    for error in document.findall("errors/error"):
        locations = []
        for row in error.findall("location"):
            path = str(row.get("file") or "").removeprefix(source_prefix).removeprefix("./")
            line = int(row.get("line") or 0)
            if path in members and line > 0:
                locations.append({"path": path, "line": line, "column": int(row.get("column") or 0)})
        rule = error.get("id") or ""
        limited = error.get("severity") == "information" or rule in {
            "syntaxError", "internalError", "internalAstError", "cppcheckError", "preprocessorError", "preprocessorErrorDirective", "unknownMacro", "checkersReport",
        }
        if limited or not locations:
            message = error.get("msg") or ""
            limitations.append({"rule_id": rule, "message": message, "locations": locations})
            if rule == "checkersReport":
                # The same native rule reports both inventory and critical
                # preprocessing failure. Preserve its exact ID/message and add
                # an adapter limitation when checker execution is unproved.
                match = re.fullmatch(r"Active checkers: ([0-9]{1,8})/([0-9]{1,8}) "
                    r"\(use --checkers-report=<filename> to see details\)", message)
                if (error.get("severity") != "information" or match is None
                        or not 0 < int(match[1]) <= int(match[2])):
                    limitations.append({"rule_id": "native_checkers_unproven",
                        "native_rule_id": rule, "message": message, "locations": locations})
            continue
        severity = {"error": "high", "warning": "medium", "style": "low", "performance": "low", "portability": "low"}.get(error.get("severity"), "unknown")
        findings.append({"rule_id": rule, **locations[0], "locations": locations,
            "message": error.get("msg") or "", "severity": severity, "native_severity": error.get("severity"),
            "cwe": error.get("cwe"), "inconclusive": error.get("inconclusive") == "true",
            "classification": "review_required_candidate", "specialist_review_completed": False})
    checked = {match.group(1).removeprefix(source_prefix).removeprefix("./")
        for match in re.finditer(r"^Checking (.+?) \.\.\.$", progress, re.M)}
    if checked - members:
        limitations.append({"rule_id": "unexpected_target", "message": "Native target is outside the frozen population.",
                            "paths": sorted(checked - members)})
    observed = sorted(checked & members)
    return findings, limitations, observed
