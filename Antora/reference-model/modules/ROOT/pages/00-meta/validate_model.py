#!/usr/bin/env python3
"""
Reference model validator for this repository.

Purpose
- Validate only the modeled part of the repository: `00-meta/` and `domains/`.
- Keep validator-owned baselines inside this file instead of modifying `00-meta/`.
- Fail when the model changed and the validator hash snapshot was not refreshed.

Scope
- Root-level noise is ignored on purpose.
- The validator does not treat root files or directories outside `00-meta/` and `domains/`
  as part of the canonical model.
- The validator is intentionally self-contained: rules, hash baselines and update logic
  live in this file.

Commands
- `python3 00-meta/validate_model.py check`
- `python3 00-meta/validate_model.py update-hashes --kind all`
- `python3 00-meta/validate_model.py update-hashes --kind meta`
- `python3 00-meta/validate_model.py update-hashes --kind layers`
- `python3 00-meta/validate_model.py update-hashes --kind layers-summary`

What `check` does
- Validates the `00-meta/` structure and file naming.
- Validates the `domains/` structure and card file naming when `domains/` exists.
- Parses domain cards and validates AsciiDoc structure, YAML schema and selected enums.
- Validates selected internal references.
- Validates child-domain minimum objects and `.summary` declarations.
- Recomputes embedded hashes for `00-meta/`, `00-meta/layers/` and
  `00-meta/layers-summary/` and compares them with the snapshot stored in this file.
- Runs semantic sync checks between canonical layer docs and key summary docs.

What `update-hashes` does
- Runs the repository validation without comparing against the currently embedded hashes.
- Refuses to write new hashes if the repository is structurally or semantically invalid.
- Rewrites the embedded hash snapshot inside this file.
- `layers` updates `layers_full` and `meta_full`.
- `layers-summary` updates `layers_summary_full` and `meta_full`.
- `all` updates all embedded hashes.

Done
- Root validation scope limited to `00-meta/` and `domains/`.
- Structure validation for `00-meta/` and domain trees.
- Naming validation for root meta docs, layer docs and domain cards.
- Layer metadata extraction from `00-meta/layers/*.adoc`.
- Semantic sync checks for:
    - `00-meta/layers-summary/LAYER-CANONICAL-TABLES-002.adoc`
    - `00-meta/layers-summary/OBJECT-PREFIX-REGISTRY-001.adoc`
    - `00-meta/layers-summary/LAYER-SPECIAL-FIELDS-001.adoc`
- Domain card validation:
    - required AsciiDoc sections and order
  - fenced YAML block
  - required base fields
  - selected enum checks
  - selected layer-specific field checks
  - file name to YAML consistency
  - selected internal-reference checks
- Child-domain validation:
    - `parent_domain`
        - minimum own objects in `.summary`, `08`, `24`, `25`
  - `used_layers` / `unused_layers` coverage
  - `reference_release` format and presence in the release register
- Embedded hash snapshot and self-update mode.

TODO
- Deeper cross-layer traceability-chain validation for all layer contracts.
- Richer artifact file validation, including notation metadata inside source artifacts.
- More precise semantic comparison between prose and YAML beyond duplicated status fields.
- Optional git-aware changed-files mode.
- Optional machine-readable output mode.
- Optional stricter `indexes/` validation when index naming rules are formalized.
"""

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import yaml


SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent.resolve()
ROOT_META_DIR = REPO_ROOT / "00-meta"
DOMAINS_DIR = REPO_ROOT / "domains"
DOMAIN_SUMMARY_DIR_NAME = ".summary"

HASH_ALGORITHM = "sha256"

RE_LAYER_DOC = re.compile(r"^(?P<code>\d{2})-(?P<slug>[a-z0-9-]+)\.adoc$")
RE_META_DOC = re.compile(r"^[A-Z0-9-]+-\d{3}\.adoc$")
RE_DOMAIN_NAME = re.compile(r"^[a-z0-9-]+$")
RE_INDEX_DOC = re.compile(r"^(?:[A-Z0-9-]+-\d{3}|[A-Z0-9]+-[A-Z0-9-]+-\d{3}-[a-z0-9-]+)\.adoc$")
RE_CARD_FILENAME = re.compile(
    r"^(?P<prefix>[A-Z0-9]+)-(?P<domain>[A-Z0-9-]+)-(?P<number>\d{3})-(?P<slug>[a-z0-9-]+)\.adoc$"
)
RE_CARD_VERSION = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RE_LAYER_CODE = re.compile(r"^\d{2}$")
RE_RELEASE_ID = re.compile(r"^RM-\d{8}-\d{3}$")
RE_YAML_BLOCK = re.compile(r"(?:```(?:yaml)?\n(.*?)\n```|\[source(?:,yaml)?\]\n----\n(.*?)\n----)", re.DOTALL)
RE_H1 = re.compile(r"^=\s+(.+?)\s*$", re.MULTILINE)
RE_H2 = re.compile(r"^==\s+(.+?)\s*$", re.MULTILINE)
RE_CODE_SPAN = re.compile(r"`([^`]+)`")
RE_DOC_LINK = re.compile(r"(?:\[[^\]]+\]\(([^)]+)\)|(?:xref|link):([^\[]+)\[[^\]]*\])")

REQUIRED_MODEL_ROOTS = ("00-meta", "domains")
ALLOWED_META_SECTIONS = {
    "governance",
    "layers",
    "layers-summary",
    "naming-rules",
    "repository-structure",
    "schemas",
    "templates",
    "traceability-rules",
}
ALLOWED_META_ROOT_FILES = {"validate_model.py"}

REQUIRED_CARD_SECTIONS = [
    "Краткое описание",
    "Текущее состояние",
    "Что подтверждено",
    "Замечания аналитика",
    "Требуемые изменения",
    "Решение по карточке",
    "Связанные объекты",
    "Источники",
    "Артефакты",
    "Технические поля",
]

NULL_REFERENCE_TOKENS = {"none"}

REQUIRED_BASE_FIELDS = {
    "Полное_имя_файла",
    "type",
    "layer",
    "name",
    "title",
    "status",
    "version",
    "owner",
    "domain",
    "tags",
    "summary",
    "description",
    "card_status",
    "validation_status",
    "change_status",
    "approval_status",
    "current_state_text",
    "validated_facts_text",
    "validation_notes_text",
    "change_request_text",
    "relations",
    "created_at",
    "updated_at",
    "validated_by",
    "validated_at",
    "approved_by",
    "approved_at",
}

OPTIONAL_LIST_FIELDS = {
    "source_refs",
    "artifact_refs",
    "refusal_reasons",
    "resulting_risk_refs",
}

OPTIONAL_MAPPING_FIELDS = {
    "artifact_notations",
}

STATUS_ENUMS = {
    "status": {"draft", "review", "approved", "obsolete", "archived"},
    "card_status": {"draft", "review", "approved", "obsolete", "archived"},
    "validation_status": {
        "not_validated",
        "validated",
        "partially_validated",
        "rejected",
        "needs_clarification",
    },
    "change_status": {
        "no_change",
        "change_identified",
        "new_requirement",
        "approved_for_implementation",
        "in_implementation",
        "implemented",
        "in_testing",
        "tested_failed",
        "tested_passed",
        "accepted",
        "cancelled",
    },
    "approval_status": {"not_submitted", "submitted", "approved", "rejected"},
    "mandatory_input_status": {"complete", "partial", "refused", "not_applicable"},
}

BOOLEAN_ENUMS = {
    "critical_path": {"true", "false"},
    "critical_path_metric": {"true", "false"},
}

SHARED_LAYER_27_33_DECISIONS = {
    "within_constraints",
    "changes_required",
    "constraint_violation",
    "unknown",
    "not_applicable",
}

FIELD_ENUMS = {
    "record_mode": {"baseline_constraint", "initiative_assessment", "mixed"},
    "hypothesis_status": {"proposed", "under_evaluation", "promoted_to_requirement", "rejected", "parked"},
    "criticality_level": {"mission-critical", "business-critical", "important", "supporting"},
    "scenario_type": {"primary", "alternate", "failure", "degraded", "recovery"},
    "criticality": {"critical-path", "high", "medium", "low"},
}

INTERNAL_REFERENCE_FIELDS = {
    "source_refs",
    "resulting_risk_refs",
    "affected_requirement_refs",
    "impacted_constraint_refs",
    "critical_path_refs",
    "failure_scenario_refs",
    "acceptance_criteria_refs",
    "fallback_process_refs",
    "critical_path_step_refs",
    "assessment_subject_refs",
}

SUMMARY_SPECIAL_FIELD_SECTION_RE = re.compile(r"^===\s+`(?P<title>\d{2}[^`]*)`\s*$")
HASH_BLOCK_RE = re.compile(
    r"(?ms)^# BEGIN EMBEDDED HASHES\n.*?^# END EMBEDDED HASHES$"
)

HASH_KIND_TO_KEYS = {
    "meta": {"meta_full"},
    "layers": {"layers_full", "meta_full"},
    "layers-summary": {"layers_summary_full", "meta_full"},
    "all": {"meta_full", "layers_full", "layers_summary_full"},
}
HASH_KEY_TO_PATH = {
    "meta_full": ROOT_META_DIR,
    "layers_full": ROOT_META_DIR / "layers",
    "layers_summary_full": ROOT_META_DIR / "layers-summary",
}

# BEGIN EMBEDDED HASHES
EMBEDDED_HASHES = {
    "layers_full": "a1579c36074a0dd704024672b7e11f0fd149f705dabc5a2525de1fa5d2045d17",
    "layers_summary_full": "377ffb6fc39101d4835e761da82c4d2ed66d833818ada4b829b02b75391bfc3c",
    "meta_full": "849dd77ea002a6f65b3715763f7c8f3dc14afde4dcc341201163eae90b8ad5db",
}
# END EMBEDDED HASHES


@dataclass
class ValidationIssue:
    code: str
    path: str
    message: str


@dataclass
class CardCandidate:
    path: Path
    domain_root: Path
    layer_code: str
    layer_dir_name: str


@dataclass
class DomainRecord:
    root: Path
    parent_name: Optional[str]


@dataclass
class LayerInfo:
    code: str
    file_name: str
    slug: str
    title: str
    canonical_path: str
    domain_dir_name: str
    prefixes: Set[str] = field(default_factory=set)
    special_fields: List[str] = field(default_factory=list)


@dataclass
class CardData:
    candidate: CardCandidate
    prefix: str
    file_domain_token: str
    number: str
    slug: str
    object_id: str
    title: str
    section_order: List[str]
    section_content: Dict[str, str]
    yaml_data: Dict[str, Any]


@dataclass
class ValidationContext:
    issues: List[ValidationIssue] = field(default_factory=list)
    card_candidates: List[CardCandidate] = field(default_factory=list)
    domain_records: List[DomainRecord] = field(default_factory=list)
    layer_infos: Dict[str, LayerInfo] = field(default_factory=dict)

    def error(self, code: str, path: Path, message: str) -> None:
        self.issues.append(ValidationIssue(code=code, path=repo_rel(path), message=message))


def repo_rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def read_text_normalized(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")


def normalize_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value).strip()


def normalize_layer_code(value: Any) -> Optional[str]:
    if isinstance(value, int):
        return f"{value:02d}"
    if isinstance(value, str):
        stripped = value.strip()
        if re.fullmatch(r"\d{1,2}", stripped):
            return stripped.zfill(2)
    return None


def document_sections(text: str) -> Tuple[List[str], Dict[str, str]]:
    matches = list(RE_H2.finditer(text))
    order: List[str] = []
    content: Dict[str, str] = {}
    for index, match in enumerate(matches):
        section_name = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        order.append(section_name)
        content[section_name] = text[start:end].strip("\n")
    return order, content


def first_heading(text: str) -> Optional[str]:
    match = RE_H1.search(text)
    return match.group(1).strip() if match else None


def payload_for_digest(file_path: Path) -> str:
    payload = read_text_normalized(file_path)
    if file_path.resolve() == SCRIPT_PATH.resolve():
        payload = HASH_BLOCK_RE.sub(
            "# BEGIN EMBEDDED HASHES\nEMBEDDED_HASHES = {}\n# END EMBEDDED HASHES",
            payload,
            count=1,
        )
    return payload


def compute_tree_digest(root: Path) -> str:
    hasher = hashlib.sha256()
    files = sorted(path for path in root.rglob("*") if path.is_file())
    for file_path in files:
        rel = repo_rel(file_path)
        payload = payload_for_digest(file_path)
        hasher.update(rel.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(payload.encode("utf-8"))
        hasher.update(b"\0")
    return hasher.hexdigest()


def current_hashes() -> Dict[str, str]:
    return {
        "meta_full": compute_tree_digest(HASH_KEY_TO_PATH["meta_full"]),
        "layers_full": compute_tree_digest(HASH_KEY_TO_PATH["layers_full"]),
        "layers_summary_full": compute_tree_digest(HASH_KEY_TO_PATH["layers_summary_full"]),
    }


def validate_required_model_roots(ctx: ValidationContext) -> None:
    for root_name in REQUIRED_MODEL_ROOTS:
        path = REPO_ROOT / root_name
        if not path.exists():
            if root_name == "domains":
                continue
            ctx.error("missing-root", path, f"required model root `{root_name}` is missing")
        elif not path.is_dir():
            ctx.error("root-not-directory", path, f"`{root_name}` must be a directory")


def validate_meta_structure(ctx: ValidationContext) -> None:
    if not ROOT_META_DIR.exists() or not ROOT_META_DIR.is_dir():
        return

    present_sections: Set[str] = set()
    for entry in sorted(ROOT_META_DIR.iterdir(), key=lambda item: item.name):
        if not entry.is_dir():
            if entry.name in ALLOWED_META_ROOT_FILES:
                continue
            ctx.error("meta-root-file", entry, "files are not allowed directly under `00-meta/`")
            continue
        present_sections.add(entry.name)
        if entry.name not in ALLOWED_META_SECTIONS:
            ctx.error("unexpected-meta-section", entry, "unexpected directory inside `00-meta/`")
            continue
        if entry.name == "layers":
            validate_layers_section(ctx, entry)
        else:
            validate_standard_meta_section(ctx, entry)

    for required in sorted(ALLOWED_META_SECTIONS):
        if required not in present_sections:
            ctx.error("missing-meta-section", ROOT_META_DIR / required, "required `00-meta` section is missing")


def validate_standard_meta_section(ctx: ValidationContext, section_dir: Path) -> None:
    for entry in sorted(section_dir.iterdir(), key=lambda item: item.name):
        if entry.is_dir():
            ctx.error("nested-meta-directory", entry, "nested directories are not allowed in this `00-meta` section")
            continue
        if not RE_META_DOC.match(entry.name):
            ctx.error(
                "invalid-meta-doc-name",
                entry,
                "file name must match `00-meta/<section>/[A-Z0-9-]+-\\d{3}.adoc`",
            )


def validate_layers_section(ctx: ValidationContext, layers_dir: Path) -> None:
    codes_found: Dict[str, Path] = {}
    for entry in sorted(layers_dir.iterdir(), key=lambda item: item.name):
        if entry.is_dir():
            ctx.error("nested-layer-directory", entry, "nested directories are not allowed in `00-meta/layers/`")
            continue
        match = RE_LAYER_DOC.match(entry.name)
        if not match:
            ctx.error(
                "invalid-layer-doc-name",
                entry,
                "file name must match `00-meta/layers/\\d{2}-[a-z0-9-]+.adoc`",
            )
            continue
        code = match.group("code")
        if int(code) > 33:
            ctx.error("invalid-layer-code", entry, "layer code must be within the canonical range `00..33`")
            continue
        if code in codes_found:
            ctx.error("duplicate-layer-code", entry, f"duplicate layer code `{code}` in `00-meta/layers/`")
            continue
        codes_found[code] = entry

    for numeric_code in range(34):
        code = f"{numeric_code:02d}"
        if code not in codes_found:
            ctx.error("missing-layer-doc", layers_dir / f"{code}-*.adoc", f"missing canonical layer doc for layer `{code}`")


def parse_layer_info(ctx: ValidationContext) -> Dict[str, LayerInfo]:
    layer_infos: Dict[str, LayerInfo] = {}
    layers_dir = ROOT_META_DIR / "layers"
    if not layers_dir.exists():
        return layer_infos

    for entry in sorted(layers_dir.iterdir(), key=lambda item: item.name):
        match = RE_LAYER_DOC.match(entry.name)
        if not match:
            continue
        code = match.group("code")
        slug = match.group("slug")
        try:
            text = read_text_normalized(entry)
        except OSError as exc:
            ctx.error("layer-read-failed", entry, f"failed to read layer doc: {exc}")
            continue
        title = first_heading(text)
        if not title:
            ctx.error("layer-missing-title", entry, "layer doc must start with an H1 heading")
            continue
        section_order, sections = document_sections(text)
        path_section = sections.get("Path", "")
        path_values = RE_CODE_SPAN.findall(path_section)
        if not path_values:
            ctx.error("layer-missing-path", entry, "layer doc must declare canonical path in the `Path` section")
            continue
        canonical_path = path_values[0].strip()
        domain_dir_name = Path(canonical_path.rstrip("/")).name

        prefixes: Set[str] = set()
        for line in sections.get("Typical objects", "").splitlines():
            prefixes.update(re.findall(r"`([A-Z][A-Z0-9]*)-\*`", line))

        special_fields: List[str] = []
        for line in sections.get("Special fields", "").splitlines():
            match_field = re.match(r"^\s*-\s+`([^`]+)`", line)
            if match_field:
                special_fields.append(match_field.group(1).strip())

        layer_infos[code] = LayerInfo(
            code=code,
            file_name=entry.name,
            slug=slug,
            title=title,
            canonical_path=canonical_path,
            domain_dir_name=domain_dir_name,
            prefixes=prefixes,
            special_fields=special_fields,
        )

    return layer_infos


def parse_asciidoc_table_rows(text: str) -> List[List[str]]:
    rows: List[List[str]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("|") or line == "|===":
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if not cells:
            continue
        if all(set(cell) <= {"-", ":"} for cell in cells):
            continue
        rows.append(cells)
    return rows


def validate_layers_summary_sync(ctx: ValidationContext, layer_infos: Dict[str, LayerInfo]) -> None:
    if not layer_infos:
        return
    validate_summary_canonical_table(ctx, layer_infos)
    validate_summary_prefix_registry(ctx, layer_infos)
    validate_summary_special_fields(ctx, layer_infos)


def validate_summary_canonical_table(ctx: ValidationContext, layer_infos: Dict[str, LayerInfo]) -> None:
    path = ROOT_META_DIR / "layers-summary" / "LAYER-CANONICAL-TABLES-002.adoc"
    if not path.exists():
        ctx.error("missing-summary-doc", path, "missing key summary doc `LAYER-CANONICAL-TABLES-002.adoc`")
        return
    rows = parse_asciidoc_table_rows(read_text_normalized(path))
    by_code: Dict[str, List[str]] = {}
    for row in rows:
        if len(row) < 6:
            continue
        code = row[0].strip()
        if RE_LAYER_CODE.match(code):
            by_code[code] = row

    for code, info in sorted(layer_infos.items()):
        row = by_code.get(code)
        if not row:
            ctx.error("missing-summary-row", path, f"missing summary row for layer `{code}`")
            continue
        actual_canonical_path = row[4].strip().strip("`")
        if actual_canonical_path != info.canonical_path:
            ctx.error(
                "summary-path-mismatch",
                path,
                f"layer `{code}` canonical path mismatch: expected `{info.canonical_path}`, found `{actual_canonical_path}`",
            )
        link_match = RE_DOC_LINK.search(row[5])
        expected_links = {
            f"../layers/{info.file_name}",
            f"00-meta/layers/{info.file_name}",
        }
        actual_link = (link_match.group(1) or link_match.group(2)).strip() if link_match else ""
        if actual_link not in expected_links:
            ctx.error(
                "summary-link-mismatch",
                path,
                f"layer `{code}` static-doc link mismatch: expected one of `{sorted(expected_links)}`, found `{actual_link or 'missing'}`",
            )


def parse_prefix_registry(path: Path) -> Dict[str, Set[str]]:
    rows = parse_asciidoc_table_rows(read_text_normalized(path))
    registry: Dict[str, Set[str]] = {}
    for row in rows:
        if len(row) < 2:
            continue
        code = row[0].strip()
        if not RE_LAYER_CODE.match(code):
            continue
        prefixes = set(re.findall(r"`([A-Z][A-Z0-9]*)`", row[1]))
        registry[code] = prefixes
    return registry


def validate_summary_prefix_registry(ctx: ValidationContext, layer_infos: Dict[str, LayerInfo]) -> None:
    path = ROOT_META_DIR / "layers-summary" / "OBJECT-PREFIX-REGISTRY-001.adoc"
    if not path.exists():
        ctx.error("missing-summary-doc", path, "missing key summary doc `OBJECT-PREFIX-REGISTRY-001.adoc`")
        return
    registry = parse_prefix_registry(path)
    for code, info in sorted(layer_infos.items()):
        actual = registry.get(code)
        if actual is None:
            ctx.error("missing-prefix-row", path, f"missing prefix registry row for layer `{code}`")
            continue
        if actual != info.prefixes:
            ctx.error(
                "prefix-registry-mismatch",
                path,
                f"layer `{code}` prefixes mismatch: expected `{sorted(info.prefixes)}`, found `{sorted(actual)}`",
            )


def parse_special_fields_summary(path: Path) -> Dict[str, List[str]]:
    text = read_text_normalized(path)
    mapping: Dict[str, List[str]] = {}
    current_code: Optional[str] = None
    current_fields: List[str] = []
    for line in text.splitlines():
        heading_match = SUMMARY_SPECIAL_FIELD_SECTION_RE.match(line.strip())
        if heading_match:
            if current_code is not None:
                mapping[current_code] = current_fields
            title = heading_match.group("title")
            current_code = title[:2]
            current_fields = []
            continue
        if current_code is None:
            continue
        field_match = re.match(r"^\s*-\s+`([^`]+)`", line)
        if field_match:
            current_fields.append(field_match.group(1).strip())
        elif line.startswith("== "):
            mapping[current_code] = current_fields
            current_code = None
            current_fields = []
    if current_code is not None:
        mapping[current_code] = current_fields
    return mapping


def validate_summary_special_fields(ctx: ValidationContext, layer_infos: Dict[str, LayerInfo]) -> None:
    path = ROOT_META_DIR / "layers-summary" / "LAYER-SPECIAL-FIELDS-001.adoc"
    if not path.exists():
        ctx.error("missing-summary-doc", path, "missing key summary doc `LAYER-SPECIAL-FIELDS-001.adoc`")
        return
    summary_fields = parse_special_fields_summary(path)
    for code, info in sorted(layer_infos.items()):
        expected = info.special_fields
        actual = summary_fields.get(code, [])
        if expected != actual:
            ctx.error(
                "special-fields-mismatch",
                path,
                f"layer `{code}` special fields mismatch: expected `{expected}`, found `{actual}`",
            )


def validate_domains(ctx: ValidationContext, layer_infos: Dict[str, LayerInfo]) -> None:
    if not DOMAINS_DIR.exists() or not DOMAINS_DIR.is_dir():
        return
    if not layer_infos:
        ctx.error("missing-layer-metadata", ROOT_META_DIR / "layers", "cannot validate domains without parsed layer metadata")
        return

    expected_layer_dirs = {info.domain_dir_name for info in layer_infos.values()}
    # `indexes/` is part of the canonical domain structure, but it is populated-only in practice:
    # Git does not preserve empty directories, so requiring an empty `indexes/` would make clean CI
    # checkouts fail even when the domain has no actual index files yet.
    required_domain_dirs = {DOMAIN_SUMMARY_DIR_NAME, "artifacts"}
    allowed_domain_dirs = set(required_domain_dirs) | {"domains", "indexes"}
    allowed_domain_dirs.update(expected_layer_dirs)

    for entry in sorted(DOMAINS_DIR.iterdir(), key=lambda item: item.name):
        if not entry.is_dir():
            ctx.error("domains-root-file", entry, "only domain directories are allowed directly under `domains/`")
            continue
        if not RE_DOMAIN_NAME.match(entry.name):
            ctx.error("invalid-domain-name", entry, "domain directory name must match `[a-z0-9-]+`")
            continue
        validate_domain_tree(ctx, entry, None, layer_infos, required_domain_dirs, allowed_domain_dirs)


def validate_domain_tree(
    ctx: ValidationContext,
    domain_root: Path,
    parent_name: Optional[str],
    layer_infos: Dict[str, LayerInfo],
    required_domain_dirs: Set[str],
    allowed_domain_dirs: Set[str],
) -> None:
    ctx.domain_records.append(DomainRecord(root=domain_root, parent_name=parent_name))

    for required_dir in sorted(required_domain_dirs):
        required_path = domain_root / required_dir
        if not required_path.exists():
            ctx.error("missing-domain-dir", required_path, f"required domain directory `{required_dir}` is missing")
        elif not required_path.is_dir():
            ctx.error("domain-entry-not-dir", required_path, f"`{required_dir}` must be a directory")

    for entry in sorted(domain_root.iterdir(), key=lambda item: item.name):
        if not entry.is_dir():
            ctx.error("domain-root-file", entry, "files are not allowed directly under a domain root")
            continue
        if entry.name not in allowed_domain_dirs:
            ctx.error("unexpected-domain-dir", entry, "unexpected directory inside domain root")
            continue

        if entry.name == "domains":
            validate_child_domain_container(ctx, entry, domain_root.name, layer_infos, required_domain_dirs, allowed_domain_dirs)
            continue
        if entry.name == "artifacts":
            continue
        if entry.name == "indexes":
            validate_indexes_dir(ctx, entry)
            continue

        layer_code = layer_code_for_domain_dir(layer_infos, entry.name)
        if layer_code is None:
            ctx.error("unknown-layer-dir", entry, "directory is not recognized as a canonical layer directory")
            continue
        validate_domain_card_dir(ctx, domain_root, entry, layer_code)


def validate_child_domain_container(
    ctx: ValidationContext,
    container: Path,
    parent_name: str,
    layer_infos: Dict[str, LayerInfo],
    required_domain_dirs: Set[str],
    allowed_domain_dirs: Set[str],
) -> None:
    for entry in sorted(container.iterdir(), key=lambda item: item.name):
        if not entry.is_dir():
            ctx.error("child-domain-file", entry, "only child-domain directories are allowed under `domains/<parent>/domains/`")
            continue
        if not RE_DOMAIN_NAME.match(entry.name):
            ctx.error("invalid-domain-name", entry, "child-domain directory name must match `[a-z0-9-]+`")
            continue
        validate_domain_tree(ctx, entry, parent_name, layer_infos, required_domain_dirs, allowed_domain_dirs)


def validate_indexes_dir(ctx: ValidationContext, indexes_dir: Path) -> None:
    for entry in sorted(indexes_dir.iterdir(), key=lambda item: item.name):
        if entry.is_dir():
            ctx.error("nested-index-directory", entry, "nested directories are not allowed in `indexes/`")
            continue
        if not RE_INDEX_DOC.match(entry.name):
            ctx.error(
                "invalid-index-doc-name",
                entry,
                "index file name must match `[A-Z0-9-]+-\\d{3}.adoc` or the standard card pattern",
            )


def layer_code_for_domain_dir(layer_infos: Dict[str, LayerInfo], dir_name: str) -> Optional[str]:
    for code, info in layer_infos.items():
        if info.domain_dir_name == dir_name:
            return code
    return None


def validate_domain_card_dir(ctx: ValidationContext, domain_root: Path, layer_dir: Path, layer_code: str) -> None:
    for entry in sorted(layer_dir.iterdir(), key=lambda item: item.name):
        if entry.is_dir():
            ctx.error("nested-card-directory", entry, "nested directories are not allowed inside a layer directory")
            continue
        if not RE_CARD_FILENAME.match(entry.name):
            ctx.error(
                "invalid-card-name",
                entry,
                "card file name must match `[PREFIX]-[DOMAIN]-[NNN]-[slug].adoc` with uppercase prefix/domain and lowercase slug",
            )
            continue
        ctx.card_candidates.append(
            CardCandidate(
                path=entry,
                domain_root=domain_root,
                layer_code=layer_code,
                layer_dir_name=layer_dir.name,
            )
        )


def build_root_doc_id_set() -> Set[str]:
    object_ids: Set[str] = set()
    for section_name in ALLOWED_META_SECTIONS:
        if section_name == "layers":
            continue
        section_dir = ROOT_META_DIR / section_name
        if not section_dir.exists():
            continue
        for entry in section_dir.iterdir():
            if entry.is_file() and RE_META_DOC.match(entry.name):
                object_ids.add(entry.stem)
    return object_ids


def parse_release_ids() -> Set[str]:
    register_path = ROOT_META_DIR / "governance" / "REFERENCE-MODEL-RELEASE-REGISTER-001.adoc"
    if not register_path.exists():
        return set()
    text = read_text_normalized(register_path)
    return set(re.findall(r"\bRM-\d{8}-\d{3}\b", text))


def parse_cards(ctx: ValidationContext) -> List[CardData]:
    cards: List[CardData] = []
    for candidate in ctx.card_candidates:
        match = RE_CARD_FILENAME.match(candidate.path.name)
        if not match:
            continue
        try:
            text = read_text_normalized(candidate.path)
        except OSError as exc:
            ctx.error("card-read-failed", candidate.path, f"failed to read card: {exc}")
            continue

        title = first_heading(text)
        if not title:
            ctx.error("missing-card-title", candidate.path, "card must start with an H1 heading")
            continue

        section_order, section_content = document_sections(text)
        if "Краткое описание" not in section_content:
            ctx.error(
                "missing-card-section",
                candidate.path,
                "card must contain `## Краткое описание`",
            )
            continue

        if "Технические поля" not in section_content:
            ctx.error(
                "missing-card-section",
                candidate.path,
                "card must contain `## Технические поля`",
            )
            continue

        observed_canonical_order = [section_name for section_name in section_order if section_name in REQUIRED_CARD_SECTIONS]
        expected_canonical_order = [section_name for section_name in REQUIRED_CARD_SECTIONS if section_name in section_content]
        if observed_canonical_order != expected_canonical_order:
            ctx.error(
                "card-section-order",
                candidate.path,
                "canonical sections, when present, must preserve the standard relative order",
            )
            continue

        tech_fields_section = section_content.get("Технические поля", "")
        yaml_match = RE_YAML_BLOCK.search(tech_fields_section)
        if not yaml_match:
            ctx.error("missing-yaml-block", candidate.path, "`== Технические поля` must contain a YAML source block")
            continue

        yaml_payload = next((group for group in yaml_match.groups() if group is not None), None)
        if yaml_payload is None:
            ctx.error("missing-yaml-block", candidate.path, "`== Технические поля` must contain a YAML source block")
            continue

        try:
            yaml_data = yaml.safe_load(yaml_payload)
        except yaml.YAMLError as exc:
            ctx.error("invalid-yaml", candidate.path, f"invalid YAML in `Технические поля`: {exc}")
            continue
        if not isinstance(yaml_data, dict):
            ctx.error("yaml-not-mapping", candidate.path, "technical fields YAML must load as a mapping")
            continue

        prefix = match.group("prefix")
        file_domain_token = match.group("domain")
        number = match.group("number")
        slug = match.group("slug")
        object_id = f"{prefix}-{file_domain_token}-{number}"

        cards.append(
            CardData(
                candidate=candidate,
                prefix=prefix,
                file_domain_token=file_domain_token,
                number=number,
                slug=slug,
                object_id=object_id,
                title=title,
                section_order=section_order,
                section_content=section_content,
                yaml_data=yaml_data,
            )
        )
    return cards


def validate_cards(ctx: ValidationContext, cards: List[CardData], release_ids: Set[str]) -> None:
    root_doc_ids = build_root_doc_id_set()
    known_ids = set(root_doc_ids)
    seen_card_ids: Dict[str, Path] = {}

    for card in cards:
        if card.object_id in seen_card_ids:
            ctx.error(
                "duplicate-object-id",
                card.candidate.path,
                f"duplicate object id `{card.object_id}` also used in `{repo_rel(seen_card_ids[card.object_id])}`",
            )
        else:
            seen_card_ids[card.object_id] = card.candidate.path
            known_ids.add(card.object_id)

    for card in cards:
        validate_card_payload(ctx, card, release_ids)
    for card in cards:
        validate_card_references(ctx, card, known_ids)

    validate_domain_level_constraints(ctx, cards)


def validate_card_payload(ctx: ValidationContext, card: CardData, release_ids: Set[str]) -> None:
    data = card.yaml_data
    missing_fields = sorted(REQUIRED_BASE_FIELDS - set(data.keys()))
    if missing_fields:
        ctx.error("missing-required-fields", card.candidate.path, f"missing required YAML fields: {missing_fields}")
        return

    if normalize_scalar(data.get("Полное_имя_файла")) != card.candidate.path.name:
        ctx.error("filename-mismatch", card.candidate.path, "`Полное_имя_файла` must match the actual file name")

    if normalize_scalar(data.get("title")) != card.title:
        ctx.error("title-mismatch", card.candidate.path, "YAML `title` must match the AsciiDoc H1 title")

    version_value = normalize_scalar(data.get("version"))
    if not RE_CARD_VERSION.match(version_value):
        ctx.error(
            "invalid-version-format",
            card.candidate.path,
            "YAML `version` must use the calendar format `YYYY-MM-DD`",
        )

    layer_value = normalize_scalar(data.get("layer"))
    if not layer_value.startswith(card.candidate.layer_code):
        ctx.error(
            "layer-field-mismatch",
            card.candidate.path,
            f"YAML `layer` must start with layer code `{card.candidate.layer_code}`",
        )

    validate_expected_types(ctx, card)
    validate_standard_enums(ctx, card)
    validate_layer_specific_expectations(ctx, card)
    validate_decision_section_mirror(ctx, card)

    mandatory_status = normalize_scalar(data.get("mandatory_input_status"))
    refusal_reasons = data.get("refusal_reasons")
    resulting_risks = data.get("resulting_risk_refs")
    if mandatory_status in {"partial", "refused"}:
        if not isinstance(refusal_reasons, list) or not refusal_reasons:
            ctx.error(
                "missing-refusal-reasons",
                card.candidate.path,
                "`mandatory_input_status` set to `partial` or `refused` requires non-empty `refusal_reasons`",
            )
        if not isinstance(resulting_risks, list) or not resulting_risks:
            ctx.error(
                "missing-resulting-risks",
                card.candidate.path,
                "`mandatory_input_status` set to `partial` or `refused` requires non-empty `resulting_risk_refs`",
            )

    artifact_refs = data.get("artifact_refs")
    artifact_notations = data.get("artifact_notations")
    if isinstance(artifact_refs, list) and artifact_refs:
        if not isinstance(artifact_notations, dict) or not artifact_notations:
            ctx.error(
                "missing-artifact-notations",
                card.candidate.path,
                "non-empty `artifact_refs` requires non-empty `artifact_notations`",
            )
        else:
            missing_notations = sorted(ref for ref in artifact_refs if ref not in artifact_notations)
            if missing_notations:
                ctx.error(
                    "artifact-notation-coverage",
                    card.candidate.path,
                    f"`artifact_notations` must define notation for every artifact ref, missing: {missing_notations}",
                )
        if not normalize_scalar(data.get("artifact_style_reference")):
            ctx.error(
                "missing-artifact-style-reference",
                card.candidate.path,
                "non-empty `artifact_refs` requires `artifact_style_reference`",
            )

    if card.candidate.layer_code == "00":
        validate_meta_card_fields(ctx, card, release_ids)


def validate_expected_types(ctx: ValidationContext, card: CardData) -> None:
    data = card.yaml_data
    list_fields = ["tags"]
    for field_name in list_fields:
        if not isinstance(data.get(field_name), list):
            ctx.error("invalid-field-type", card.candidate.path, f"`{field_name}` must be a YAML list")

    for field_name in OPTIONAL_LIST_FIELDS:
        if field_name in data and not isinstance(data.get(field_name), list):
            ctx.error("invalid-field-type", card.candidate.path, f"`{field_name}` must be a YAML list")

    if not isinstance(data.get("relations"), dict):
        ctx.error("invalid-field-type", card.candidate.path, "`relations` must be a YAML mapping")
    for field_name in OPTIONAL_MAPPING_FIELDS:
        if field_name in data and not isinstance(data.get(field_name), dict):
            ctx.error("invalid-field-type", card.candidate.path, f"`{field_name}` must be a YAML mapping")


def validate_standard_enums(ctx: ValidationContext, card: CardData) -> None:
    data = card.yaml_data
    for field_name, allowed in STATUS_ENUMS.items():
        if field_name not in data:
            continue
        value = normalize_scalar(data.get(field_name))
        if value not in allowed:
            ctx.error(
                "invalid-enum",
                card.candidate.path,
                f"`{field_name}` must be one of {sorted(allowed)}, found `{value}`",
            )

    for field_name, allowed in FIELD_ENUMS.items():
        if field_name not in data:
            continue
        value = normalize_scalar(data.get(field_name))
        if value and value not in allowed:
            ctx.error(
                "invalid-enum",
                card.candidate.path,
                f"`{field_name}` must be one of {sorted(allowed)}, found `{value}`",
            )

    for field_name, allowed in BOOLEAN_ENUMS.items():
        if field_name not in data:
            continue
        value = normalize_scalar(data.get(field_name)).lower()
        if value and value not in allowed:
            ctx.error(
                "invalid-enum",
                card.candidate.path,
                f"`{field_name}` must be one of {sorted(allowed)}, found `{value}`",
            )


def validate_layer_specific_expectations(ctx: ValidationContext, card: CardData) -> None:
    layer_info = ctx.layer_infos.get(card.candidate.layer_code)
    if not layer_info:
        ctx.error("unknown-layer", card.candidate.path, f"unknown layer code `{card.candidate.layer_code}`")
        return

    if layer_info.prefixes and card.prefix not in layer_info.prefixes:
        ctx.error(
            "prefix-layer-mismatch",
            card.candidate.path,
            f"prefix `{card.prefix}` is not valid for layer `{card.candidate.layer_code}`; expected one of {sorted(layer_info.prefixes)}",
        )

    if card.candidate.layer_code in {"27", "28", "29", "30", "31", "32", "33"}:
        decision_field = next((name for name in layer_info.special_fields if name.endswith("_decision")), None)
        if decision_field:
            decision_value = normalize_scalar(card.yaml_data.get(decision_field))
            if decision_value not in SHARED_LAYER_27_33_DECISIONS:
                ctx.error(
                    "invalid-enum",
                    card.candidate.path,
                    f"`{decision_field}` must be one of {sorted(SHARED_LAYER_27_33_DECISIONS)}, found `{decision_value}`",
                )


def validate_decision_section_mirror(ctx: ValidationContext, card: CardData) -> None:
    decision_text = card.section_content.get("Решение по карточке", "")
    if not decision_text.strip():
        return
    expected_pairs = {
        "Статус карточки": "card_status",
        "Статус валидации": "validation_status",
        "Статус изменения": "change_status",
        "Статус апрува": "approval_status",
    }
    for label, field_name in expected_pairs.items():
        match = re.search(rf"^{re.escape(label)}:\s*(.+?)\s*$", decision_text, re.MULTILINE)
        if not match:
            ctx.error(
                "decision-section-missing",
                card.candidate.path,
                f"missing `{label}` line in `Решение по карточке`",
            )
            continue
        prose_value = match.group(1).strip()
        yaml_value = normalize_scalar(card.yaml_data.get(field_name))
        if prose_value != yaml_value:
            ctx.error(
                "decision-section-mismatch",
                card.candidate.path,
                f"`{label}` in prose must match YAML `{field_name}`",
            )


def validate_meta_card_fields(ctx: ValidationContext, card: CardData, release_ids: Set[str]) -> None:
    data = card.yaml_data
    used_layers = data.get("used_layers")
    unused_layers = data.get("unused_layers")
    if not isinstance(used_layers, list) or not isinstance(unused_layers, list):
        ctx.error(
            "invalid-meta-layer-coverage",
            card.candidate.path,
            "`used_layers` and `unused_layers` must both be YAML lists",
        )
    else:
        normalized_used = {normalize_layer_code(value) for value in used_layers}
        normalized_unused = {normalize_layer_code(value) for value in unused_layers}
        if None in normalized_used or None in normalized_unused:
            ctx.error(
                "invalid-layer-code-list",
                card.candidate.path,
                "`used_layers` and `unused_layers` must contain two-digit layer codes",
            )
        else:
            full_set = {f"{code:02d}" for code in range(34)}
            merged = set(normalized_used) | set(normalized_unused)
            if merged != full_set:
                missing = sorted(full_set - merged)
                extra = sorted(merged - full_set)
                ctx.error(
                    "incomplete-layer-coverage",
                    card.candidate.path,
                    f"`used_layers` + `unused_layers` must cover `00..33`; missing={missing}, extra={extra}",
                )
            overlap = sorted(set(normalized_used) & set(normalized_unused))
            if overlap:
                ctx.error(
                    "overlapping-layer-coverage",
                    card.candidate.path,
                    f"layer codes cannot appear in both `used_layers` and `unused_layers`: {overlap}",
                )

    reference_release = normalize_scalar(data.get("reference_release"))
    if reference_release:
        if not RE_RELEASE_ID.match(reference_release):
            ctx.error(
                "invalid-reference-release",
                card.candidate.path,
                "`reference_release` must match `RM-YYYYMMDD-NNN`",
            )
        elif reference_release not in release_ids:
            ctx.error(
                "unknown-reference-release",
                card.candidate.path,
                f"`reference_release` `{reference_release}` is not present in the release register",
            )


def validate_card_references(ctx: ValidationContext, card: CardData, known_ids: Set[str]) -> None:
    data = card.yaml_data
    for field_name in INTERNAL_REFERENCE_FIELDS:
        if field_name not in data:
            continue
        values = data.get(field_name)
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, str):
                ctx.error("invalid-reference-type", card.candidate.path, f"`{field_name}` must contain only string refs")
                continue
            if value not in known_ids:
                ctx.error(
                    "unknown-reference",
                    card.candidate.path,
                    f"`{field_name}` references unknown object `{value}`",
                )

    relations = data.get("relations")
    if isinstance(relations, dict):
        for relation_value in iter_relation_refs(relations):
            if relation_value not in known_ids:
                ctx.error(
                    "unknown-relation-reference",
                    card.candidate.path,
                    f"`relations` references unknown object `{relation_value}`",
                )

    artifact_style_reference = normalize_scalar(data.get("artifact_style_reference"))
    if artifact_style_reference.lower() in NULL_REFERENCE_TOKENS:
        return
    if artifact_style_reference and artifact_style_reference not in known_ids:
        ctx.error(
            "unknown-reference",
            card.candidate.path,
            f"`artifact_style_reference` references unknown object `{artifact_style_reference}`",
        )


def iter_relation_refs(value: Any) -> Iterable[str]:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                yield item
            elif isinstance(item, (list, dict)):
                for nested in iter_relation_refs(item):
                    yield nested
    elif isinstance(value, dict):
        for nested_value in value.values():
            for nested in iter_relation_refs(nested_value):
                yield nested


def validate_domain_level_constraints(ctx: ValidationContext, cards: List[CardData]) -> None:
    cards_by_domain: Dict[Path, List[CardData]] = {}
    for card in cards:
        cards_by_domain.setdefault(card.candidate.domain_root, []).append(card)

    for domain_record in ctx.domain_records:
        domain_cards = cards_by_domain.get(domain_record.root, [])
        meta_cards = [card for card in domain_cards if card.candidate.layer_code == "00" and card.prefix == "MAP"]
        if not meta_cards:
            ctx.error(
                "missing-domain-map",
                domain_record.root / DOMAIN_SUMMARY_DIR_NAME,
                "every domain must have at least one `MAP-*` card in `.summary/`",
            )

        if domain_record.parent_name is not None:
            matching_parent = False
            for meta_card in meta_cards:
                parent_value = normalize_scalar(meta_card.yaml_data.get("parent_domain"))
                if parent_value == domain_record.parent_name:
                    matching_parent = True
                    break
            if not matching_parent:
                ctx.error(
                    "parent-domain-mismatch",
                    domain_record.root / DOMAIN_SUMMARY_DIR_NAME,
                    f"child domain must declare `parent_domain: {domain_record.parent_name}` in a `MAP-*` card",
                )

            required_layer_codes = {"00", "08", "24", "25"}
            present_required = {card.candidate.layer_code for card in domain_cards if card.candidate.layer_code in required_layer_codes}
            missing = sorted(required_layer_codes - present_required)
            if missing:
                ctx.error(
                    "child-domain-minimum-objects",
                    domain_record.root,
                    f"child domain must have own objects in layers {missing}",
                )


def validate_hash_snapshot(ctx: ValidationContext, digests: Dict[str, str]) -> None:
    for key in ("meta_full", "layers_full", "layers_summary_full"):
        embedded = EMBEDDED_HASHES.get(key, "")
        current = digests[key]
        target_path = repo_rel(HASH_KEY_TO_PATH[key])
        if not embedded:
            ctx.error(
                "missing-embedded-hash",
                SCRIPT_PATH,
                f"embedded hash `{key}` is empty for `{target_path}`; run `update-hashes --kind all`",
            )
            continue
        if embedded != current:
            ctx.error(
                "stale-embedded-hash",
                SCRIPT_PATH,
                f"embedded hash `{key}` does not match current contents of `{target_path}`; validator is outdated against the model",
            )

    layers_changed = EMBEDDED_HASHES.get("layers_full") != digests["layers_full"]
    summary_changed = EMBEDDED_HASHES.get("layers_summary_full") != digests["layers_summary_full"]

    if layers_changed and not summary_changed:
        ctx.error(
            "layers-summary-sync",
            SCRIPT_PATH,
            "`00-meta/layers/` changed but `00-meta/layers-summary/` embedded digest did not; update summary docs and refresh hashes",
        )


def serialize_hash_block(hash_values: Dict[str, str]) -> str:
    ordered_keys = ["layers_full", "layers_summary_full", "meta_full"]
    lines = ["# BEGIN EMBEDDED HASHES", "EMBEDDED_HASHES = {"]
    for key in ordered_keys:
        lines.append(f'    "{key}": "{hash_values[key]}",')
    lines.append("}")
    lines.append("# END EMBEDDED HASHES")
    return "\n".join(lines)


def write_hash_snapshot(hash_values: Dict[str, str]) -> None:
    original = read_text_normalized(SCRIPT_PATH)
    replacement = serialize_hash_block(hash_values)
    updated, count = HASH_BLOCK_RE.subn(replacement, original, count=1)
    if count != 1:
        raise RuntimeError("failed to locate embedded hash block in validator source")
    SCRIPT_PATH.write_text(updated, encoding="utf-8")


def print_issues(issues: Sequence[ValidationIssue]) -> None:
    for issue in sorted(issues, key=lambda item: (item.path, item.code, item.message)):
        print(f"ERROR [{issue.code}] {issue.path}: {issue.message}")


def validate_repository(skip_hash_snapshot: bool) -> Tuple[ValidationContext, Dict[str, str]]:
    ctx = ValidationContext()
    validate_required_model_roots(ctx)
    validate_meta_structure(ctx)
    ctx.layer_infos = parse_layer_info(ctx)
    validate_layers_summary_sync(ctx, ctx.layer_infos)
    validate_domains(ctx, ctx.layer_infos)

    release_ids = parse_release_ids()
    cards = parse_cards(ctx)
    validate_cards(ctx, cards, release_ids)

    digests = current_hashes()
    if not skip_hash_snapshot:
        validate_hash_snapshot(ctx, digests)
    return ctx, digests


def command_check() -> int:
    ctx, _ = validate_repository(skip_hash_snapshot=False)
    if ctx.issues:
        print_issues(ctx.issues)
        print(f"\nValidation failed with {len(ctx.issues)} error(s).")
        return 1
    print("Validation passed.")
    return 0


def command_update_hashes(kind: str) -> int:
    ctx, digests = validate_repository(skip_hash_snapshot=True)
    if ctx.issues:
        print_issues(ctx.issues)
        print("\nHash snapshot was not updated because the repository is not valid.")
        return 1

    updated = dict(EMBEDDED_HASHES)
    for key in HASH_KIND_TO_KEYS[kind]:
        updated[key] = digests[key]
    write_hash_snapshot(updated)

    print(f"Updated embedded hashes for kind `{kind}`.")
    for key in sorted(HASH_KIND_TO_KEYS[kind]):
        print(f"- {key}: {updated[key]}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reference model validator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("check", help="Validate the repository against embedded rules and hashes")

    update_parser = subparsers.add_parser(
        "update-hashes",
        help="Recompute and embed validator-owned hashes after validation succeeds",
    )
    update_parser.add_argument(
        "--kind",
        choices=sorted(HASH_KIND_TO_KEYS.keys()),
        default="all",
        help="Which embedded hash set to refresh",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "check":
        return command_check()
    if args.command == "update-hashes":
        return command_update_hashes(args.kind)
    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
