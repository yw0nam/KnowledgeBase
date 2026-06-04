"""DB-backed wiki page validators."""

from __future__ import annotations

import re
from sqlalchemy import select
from sqlalchemy.orm import Session

from kb.db.models import Page, RawSource
from kb.lint.common import (
    IMPROVEMENT_DOMAIN_VALUES,
    IMPROVEMENT_ISSUE_STATUS_VALUES,
    IMPROVEMENT_KIND_VALUES,
    IMPROVEMENT_SEVERITY_VALUES,
    ISO_DATE_RE,
    REQUIRED_FM_FIELDS,
    REVIEW_STATUS_TYPES,
    REVIEW_STATUS_VALUES,
    STUB_THRESHOLD_CHARS,
    LintResult,
    extract_wikilinks,
    parse_frontmatter_dict,
)

LLM_TODO_RE = re.compile(r"<!--\s*LLM(?:\s+TODO)?:.*?-->", re.DOTALL)
TASK_LIST_RE = re.compile(r"^- \[[ xX]\]\s")
EMPTY_PARENS_RE = re.compile(r"\(\)")


def validate_page_create(
    fm: dict | None,
    body_md: str,
    session: Session,
    slug: str | None = None,
) -> LintResult:
    """Validate a single page at create/patch time.

    Checks that can be done without cross-page scanning.
    """
    result = LintResult()
    identifier = slug or "(unknown)"

    fm = parse_frontmatter_dict(fm)

    if fm is None:
        result.error(identifier, "missing or invalid frontmatter (must be a dict)")
        return result
    if not fm:
        result.error(identifier, "missing or empty frontmatter")
        return result

    page_type = fm.get("type")
    if not page_type:
        result.error(identifier, "missing frontmatter field: type")
        return result

    if page_type not in REQUIRED_FM_FIELDS:
        result.warn(identifier, f"unknown page type: {page_type!r}")

    required = REQUIRED_FM_FIELDS.get(page_type, [])
    for key in required:
        if key not in fm:
            result.error(identifier, f"missing required frontmatter field: {key}")

    if page_type == "improvement":
        _validate_improvement_fm(result, identifier, fm, session)

    if page_type == "checklist":
        _validate_checklist_items(result, identifier, body_md)

    if page_type in REVIEW_STATUS_TYPES:
        _validate_review_status(result, identifier, fm)

    _validate_wikilinks(result, identifier, body_md, session, slug)

    _validate_stale_sources(result, identifier, fm, session)

    _check_llm_todos(result, identifier, body_md)

    _check_stub_page(result, identifier, body_md, slug)

    _check_empty_sections(result, identifier, body_md)

    _check_empty_relation_parens(result, identifier, body_md)

    return result


def validate_page_full(session: Session) -> LintResult:
    """Full wiki scan. Checks cross-page relationships."""
    result = LintResult()
    pages = list(session.execute(select(Page)).scalars().all())
    if not pages:
        return result

    all_slugs = {p.slug for p in pages}

    outlinks: dict[str, set[str]] = {}
    inlinks: dict[str, set[str]] = {p.slug: set() for p in pages}

    for page in pages:
        links = set(extract_wikilinks(page.body_md))
        outlinks[page.slug] = links
        for link in links:
            if link in inlinks:
                inlinks[link].add(page.slug)

    for page in pages:
        identifier = page.slug

        for link in outlinks.get(page.slug, set()):
            if ".md" in link:
                result.error(identifier, f"wikilink contains .md: [[{link}]]")
            elif link == page.slug:
                result.warn(identifier, f"self-referencing wikilink: [[{link}]]")
            elif link not in all_slugs:
                result.error(identifier, f"dead wikilink: [[{link}]]")

        skip_orphan = _should_skip_orphan(page)
        if not skip_orphan and not inlinks.get(page.slug, set()):
            result.warn(identifier, "orphan page (no incoming wikilinks)")

    return result


def _validate_review_status(result: LintResult, identifier: str, fm: dict) -> None:
    rs = fm.get("review_status")
    if rs is None:
        return
    if rs not in REVIEW_STATUS_VALUES:
        result.error(
            identifier,
            f"invalid review_status: {rs!r} (must be one of {sorted(REVIEW_STATUS_VALUES)})",
        )


def _validate_improvement_fm(
    result: LintResult,
    identifier: str,
    fm: dict,
    session: Session,
) -> None:
    kind = fm.get("kind")
    if kind not in (None, "") and kind not in IMPROVEMENT_KIND_VALUES:
        result.error(
            identifier,
            f"invalid kind: {kind!r} (must be one of {sorted(IMPROVEMENT_KIND_VALUES)})",
        )

    observed_at = fm.get("observed_at")
    if observed_at not in (None, "") and not ISO_DATE_RE.match(str(observed_at)):
        result.error(
            identifier,
            f"observed_at must be ISO date YYYY-MM-DD, got {observed_at!r}",
        )

    domain = fm.get("domain")
    if domain not in (None, "") and domain not in IMPROVEMENT_DOMAIN_VALUES:
        result.error(
            identifier,
            f"invalid domain: {domain!r} (must be one of {sorted(IMPROVEMENT_DOMAIN_VALUES)})",
        )

    severity = fm.get("severity")
    if severity not in (None, "") and severity not in IMPROVEMENT_SEVERITY_VALUES:
        result.error(
            identifier,
            f"invalid severity: {severity!r} (must be one of {sorted(IMPROVEMENT_SEVERITY_VALUES)})",
        )

    issue_status = fm.get("issue_status")
    if (
        issue_status not in (None, "")
        and issue_status not in IMPROVEMENT_ISSUE_STATUS_VALUES
    ):
        result.error(
            identifier,
            f"invalid issue_status: {issue_status!r} (must be one of {sorted(IMPROVEMENT_ISSUE_STATUS_VALUES)})",
        )

    related = fm.get("related", [])
    if isinstance(related, list):
        for ref in related:
            if not isinstance(ref, str) or not ref:
                continue
            if "/" in ref:
                continue
            stem = ref[:-3] if ref.endswith(".md") else ref
            exists = session.execute(select(Page.id).where(Page.slug == stem)).scalar()
            if not exists:
                result.error(identifier, f"related: target not found: {ref}")


def _validate_checklist_items(result: LintResult, identifier: str, body: str) -> None:
    m = re.search(r"^##\s+Items\b.*$", body, re.MULTILINE)
    if not m:
        return
    section_start = m.end()
    next_h = re.search(r"^##\s+", body[section_start:], re.MULTILINE)
    section_end = section_start + next_h.start() if next_h else len(body)
    section = body[section_start:section_end]

    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        if not TASK_LIST_RE.match(stripped):
            preview = stripped[:60]
            result.error(
                identifier,
                f"checklist item not in task-list syntax: {preview!r}",
            )


def _validate_wikilinks(
    result: LintResult,
    identifier: str,
    body: str,
    session: Session,
    slug: str | None = None,
) -> None:
    links = extract_wikilinks(body)
    if not links:
        return

    existing_slugs: set[str] = set()
    if links:
        stmt = select(Page.slug).where(Page.slug.in_(links))
        existing_slugs = set(session.execute(stmt).scalars().all())

    for link in links:
        if ".md" in link:
            result.error(identifier, f"wikilink contains .md: [[{link}]]")
        elif slug is not None and link == slug:
            result.warn(identifier, f"self-referencing wikilink: [[{link}]]")
        elif link not in existing_slugs:
            result.error(
                identifier, f"dead wikilink: [[{link}]] — no page with slug {link!r}"
            )


def _validate_stale_sources(
    result: LintResult,
    identifier: str,
    fm: dict,
    session: Session,
) -> None:
    sources = fm.get("sources")
    if not isinstance(sources, list) or not sources:
        return

    existing_keys = set()
    if sources:
        stmt = select(RawSource.source_key).where(
            RawSource.source_key.in_([s for s in sources if isinstance(s, str)])
        )
        existing_keys = set(session.execute(stmt).scalars().all())

    for src in sources:
        if not isinstance(src, str):
            continue
        if src not in existing_keys:
            result.error(identifier, f"stale source: {src!r} not found in raw_sources")


def _check_llm_todos(result: LintResult, identifier: str, body: str) -> None:
    if LLM_TODO_RE.search(body):
        result.warn(identifier, "LLM TODO placeholder found in body")


def _check_stub_page(
    result: LintResult,
    identifier: str,
    body: str,
    slug: str | None = None,
) -> None:
    if slug and _is_index_page(slug):
        return
    if len(body.strip()) < STUB_THRESHOLD_CHARS:
        result.warn(
            identifier, f"stub page: body shorter than {STUB_THRESHOLD_CHARS} chars"
        )


def _check_empty_sections(result: LintResult, identifier: str, body: str) -> None:
    headings = list(re.finditer(r"^##\s+.*$", body, re.MULTILINE))
    for i, match in enumerate(headings):
        section_start = match.end()
        if i + 1 < len(headings):
            section_end = headings[i + 1].start()
        else:
            section_end = len(body)
        section_content = body[section_start:section_end].strip()
        if not section_content:
            heading_text = match.group(0).strip()
            result.warn(identifier, f"empty section: {heading_text}")


def _check_empty_relation_parens(
    result: LintResult, identifier: str, body: str
) -> None:
    m = re.search(r"^##\s+Relationships\b.*$", body, re.MULTILINE)
    if not m:
        return
    section_start = m.end()
    next_h = re.search(r"^##\s+", body[section_start:], re.MULTILINE)
    section_end = section_start + next_h.start() if next_h else len(body)
    section = body[section_start:section_end]

    if EMPTY_PARENS_RE.search(section):
        result.warn(identifier, "empty relation parens '()' in Relationships section")


def _is_index_page(slug: str) -> bool:
    """Check if slug represents an index/hub page."""
    if slug == "index" or slug == "_index":
        return True
    if slug.endswith("/_index") or slug.endswith("/index"):
        return True
    parts = slug.rsplit("/", 1)
    if len(parts) == 2:
        return parts[1] in ("_index", "index")
    return False


def _should_skip_orphan(page) -> bool:
    if _is_index_page(page.slug):
        return True
    if page.type == "summary":
        return True
    if page.review_status and page.review_status != "approved":
        return True
    return False
