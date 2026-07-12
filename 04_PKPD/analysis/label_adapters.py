"""Label adapters — pure parsers over cached response bytes.

No network, ever. Bytes in, evidence rows out, raw SHA-256 computed from the exact
bytes parsed. A label is never summarized from memory: every row carries the setid /
application number, the label version, the effective date, the exact labeled section
(LOINC-coded), and the hash of the response it was read from.

Element paths and LOINC codes were read from live DailyMed SPL responses (see
method/sources.json :: dailymed_spl_structure_probe), not from recall.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Literal, Optional

from .canonical import sha256_bytes

HL7 = "urn:hl7-org:v3"
LOINC_SYSTEM = "2.16.840.1.113883.6.1"
UNII_SYSTEM = "2.16.840.1.113883.4.9"

# Verified against live SPLs on 2026-07-11. 34084-4 (adverse reactions) is declared in
# method/safety_taxonomy_v1.json and was missing here, so labelled adverse-reaction
# material was silently uncollected.
SECTION_CODES: dict[str, str] = {
    "34066-1": "boxed_warning",
    "34070-3": "contraindication",
    "43685-7": "warning_precaution",
    "34073-7": "labeled_interaction",
    "34084-4": "adverse_reaction",
}
SECTION_NAMES: dict[str, str] = {
    "34066-1": "Boxed Warning section",
    "34070-3": "Contraindications section",
    "43685-7": "Warnings and Precautions section",
    "34073-7": "Drug Interactions section",
    "34084-4": "Adverse Reactions section",
}


class LabelParseError(ValueError):
    """The cached response is not the document shape this adapter accepts."""


@dataclass(frozen=True)
class ParsedFinding:
    finding_type: str
    finding_text: str
    labeled_section_code: str
    labeled_section_name: str
    code_system: str


LabelSource = Literal["dailymed_spl", "openfda_label", "ema_label"]


@dataclass(frozen=True)
class ParsedLabel:
    label_source: LabelSource
    setid: Optional[str]
    application_number: Optional[str]
    product_identity: str
    label_version: Optional[str]
    effective_date: Optional[str]
    active_moiety_names: list[str]
    active_moiety_unii: list[str]
    findings: list[ParsedFinding]
    raw_sha256: str
    raw_bytes: int


def _norm(text: str) -> str:
    return " ".join(text.split())


def _section_text_blocks(section: ET.Element) -> list[str]:
    """One block per labeled paragraph/list item — the unit the brief calls a finding.

    A boxed warning with three bullets is three findings, not one wall of text.
    """
    blocks: list[str] = []
    for text_el in section.findall(f"{{{HL7}}}text"):
        for child in text_el:
            tag = child.tag.split("}")[-1]
            if tag == "list":
                for item in child.findall(f"{{{HL7}}}item"):
                    t = _norm("".join(item.itertext()))
                    if t:
                        blocks.append(t)
            else:
                t = _norm("".join(child.itertext()))
                if t:
                    blocks.append(t)
        if not list(text_el):
            t = _norm("".join(text_el.itertext()))
            if t:
                blocks.append(t)
    return blocks


def parse_dailymed_spl(raw: bytes) -> ParsedLabel:
    """Parse an HL7 v3 SPL document (DailyMed /services/v2/spls/{setid}.xml)."""
    if not isinstance(raw, (bytes, bytearray)):
        raise LabelParseError("parser takes raw response bytes")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise LabelParseError(f"not well-formed XML: {exc}") from exc

    if root.tag != f"{{{HL7}}}document":
        raise LabelParseError(f"unexpected root element {root.tag!r}; expected HL7 v3 document")

    def attr(tag: str, key: str) -> Optional[str]:
        el = root.find(f"{{{HL7}}}{tag}")
        return el.get(key) if el is not None else None

    setid = attr("setId", "root")
    version = attr("versionNumber", "value")
    effective = attr("effectiveTime", "value")
    title_el = root.find(f"{{{HL7}}}title")
    title = _norm("".join(title_el.itertext())) if title_el is not None else ""

    names: list[str] = []
    uniis: list[str] = []
    for am in root.iter(f"{{{HL7}}}activeMoiety"):
        for code_node in am.iter(f"{{{HL7}}}code"):
            unii = code_node.get("code")
            if code_node.get("codeSystem") == UNII_SYSTEM and unii:
                uniis.append(unii)
        for name in am.iter(f"{{{HL7}}}name"):
            if name.text:
                names.append(_norm(name.text))

    findings: list[ParsedFinding] = []
    for section in root.iter(f"{{{HL7}}}section"):
        code_el = section.find(f"{{{HL7}}}code")
        if code_el is None:
            continue
        code = code_el.get("code")
        if code is None or code not in SECTION_CODES or code_el.get("codeSystem") != LOINC_SYSTEM:
            continue
        for block in _section_text_blocks(section):
            findings.append(
                ParsedFinding(
                    finding_type=SECTION_CODES[code],
                    finding_text=block,
                    labeled_section_code=code,
                    labeled_section_name=code_el.get("displayName") or SECTION_NAMES[code],
                    code_system=LOINC_SYSTEM,
                )
            )

    if not setid:
        raise LabelParseError("SPL has no setId — label identity cannot be bound")

    return ParsedLabel(
        label_source="dailymed_spl",
        setid=setid,
        application_number=None,
        product_identity=title or setid,
        label_version=version,
        effective_date=_iso_date(effective),
        active_moiety_names=sorted(set(names)),
        active_moiety_unii=sorted(set(uniis)),
        findings=findings,
        raw_sha256=sha256_bytes(bytes(raw)),
        raw_bytes=len(raw),
    )


def _iso_date(yyyymmdd: Optional[str]) -> Optional[str]:
    if not yyyymmdd or len(yyyymmdd) < 8 or not yyyymmdd[:8].isdigit():
        return None
    return f"{yyyymmdd[0:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]}"


# openFDA drug/label: one result object per label version.
OPENFDA_FIELDS: dict[str, str] = {
    "boxed_warning": "boxed_warning",
    "contraindications": "contraindication",
    "warnings_and_cautions": "warning_precaution",
    "drug_interactions": "labeled_interaction",
    "adverse_reactions": "adverse_reaction",
}


def parse_openfda_label(raw: bytes) -> list[ParsedLabel]:
    """Parse an openFDA /drug/label.json response (Drugs@FDA-derived SPL content)."""
    if not isinstance(raw, (bytes, bytearray)):
        raise LabelParseError("parser takes raw response bytes")
    try:
        payload: Any = json.loads(bytes(raw).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise LabelParseError(f"not valid JSON: {exc}") from exc
    if not isinstance(payload, dict) or "results" not in payload:
        raise LabelParseError("openFDA response has no 'results' array")

    raw_sha = sha256_bytes(bytes(raw))
    labels: list[ParsedLabel] = []
    for result in payload["results"]:
        of = result.get("openfda", {}) or {}
        app_numbers = of.get("application_number") or []
        brand = (of.get("brand_name") or [""])[0]
        generic = (of.get("generic_name") or [""])[0]
        findings: list[ParsedFinding] = []
        for field, finding_type in OPENFDA_FIELDS.items():
            for block in result.get(field, []) or []:
                text = _norm(str(block))
                if text:
                    findings.append(
                        ParsedFinding(
                            finding_type=finding_type,
                            finding_text=text,
                            labeled_section_code=field,
                            labeled_section_name=field,
                            code_system="openfda_field",
                        )
                    )
        labels.append(
            ParsedLabel(
                label_source="openfda_label",
                setid=result.get("set_id"),
                application_number=app_numbers[0] if app_numbers else None,
                product_identity=brand or generic or result.get("id", "unknown"),
                label_version=str(result["version"]) if result.get("version") is not None else None,
                effective_date=_iso_date(result.get("effective_time")),
                active_moiety_names=sorted({n for n in [generic] if n}),
                active_moiety_unii=sorted(set(of.get("unii") or [])),
                findings=findings,
                raw_sha256=raw_sha,
                raw_bytes=len(raw),
            )
        )
    return labels


# EMA has no equivalent public structured label API verified in this pass. The adapter
# accepts a cached, declared JSON shape so that EMA evidence has a door to come in
# through — but the shape is UNVERIFIED against a live EMA response and must be
# reviewed before any EMA record is admitted. See 04_PKPD/METHODS.md, Limitations.
EMA_ADAPTER_STATUS = "shape_declared_unverified_against_live_source"

# Until the cached shape is validated against a live EMA response, an EMA row may be
# PARSED and INSPECTED but may not become `label_supported` evidence. Flipping this to
# True is a reviewed change, not a convenience.
EMA_LABEL_SUPPORTED_ALLOWED = False

EMA_SECTIONS: dict[str, str] = {
    "4.3": "contraindication",
    "4.4": "warning_precaution",
    "4.5": "labeled_interaction",
}


def parse_ema_product_information(raw: bytes) -> ParsedLabel:
    """Parse a cached EMA SmPC extract (declared shape; see EMA_ADAPTER_STATUS)."""
    if not isinstance(raw, (bytes, bytearray)):
        raise LabelParseError("parser takes raw response bytes")
    try:
        payload = json.loads(bytes(raw).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise LabelParseError(f"not valid JSON: {exc}") from exc

    required = {"product_name", "sections"}
    if not required.issubset(payload):
        raise LabelParseError(f"EMA cached record must contain {sorted(required)}")

    findings: list[ParsedFinding] = []
    for section in payload["sections"]:
        num = str(section.get("section_number", ""))
        if num not in EMA_SECTIONS:
            continue
        for block in section.get("items", []) or []:
            text = _norm(str(block))
            if text:
                findings.append(
                    ParsedFinding(
                        finding_type=EMA_SECTIONS[num],
                        finding_text=text,
                        labeled_section_code=num,
                        labeled_section_name=str(section.get("section_title", num)),
                        code_system="ema_smpc_section",
                    )
                )
    return ParsedLabel(
        label_source="ema_label",
        setid=None,
        application_number=payload.get("procedure_number"),
        product_identity=str(payload["product_name"]),
        label_version=payload.get("revision"),
        effective_date=payload.get("revision_date"),
        active_moiety_names=sorted(set(payload.get("active_substances", []) or [])),
        active_moiety_unii=[],
        findings=findings,
        raw_sha256=sha256_bytes(bytes(raw)),
        raw_bytes=len(raw),
    )
