import json
from pathlib import Path

from .config import VaultSettings
from .index import VaultIndex
from .search import make_snippet


class VaultReader:
    def __init__(self, settings: VaultSettings):
        self.settings = settings

    def read_note(self, note_ref: str, mode: str = "outline", heading: str | None = None, query: str | None = None, page: int = 1) -> dict:
        note = self._find_note(note_ref)
        if not note:
            return {"found": False, "error": "note not found"}
        tags = json.loads(note["tags_json"])
        aliases = json.loads(note["aliases_json"])
        headings = json.loads(note["headings_json"])
        base = {
            "found": True,
            "note_id": note["note_id"],
            "path": note["path"],
            "title": note["title"],
            "tags": tags,
            "aliases": aliases,
            "headings": headings,
            "source_ref": f"{note['path']}#{note['title']}",
            "truncated": False,
            "content": "",
            "next_action_hint": "",
        }
        body = note["body"]
        if mode == "outline":
            return base
        if mode == "summary":
            callouts = extract_callouts(body)
            if callouts:
                base["content"] = callouts
            else:
                base["content"] = lead_paragraph(body)
                base["next_action_hint"] = "无摘要 callout，已回退前导段落；可用 outline 看结构或 section 读指定章节。"
            return base
        if mode == "section":
            section = select_section(body, headings, heading)
            if section.get("heading_not_found"):
                base["found"] = False
                base["error"] = "heading not found"
                base["requested_heading"] = section.get("requested_heading", "")
                base["available_headings"] = section.get("available_headings", [])
                return base
            base["heading"] = section["heading"]
            base["heading_matched"] = section["heading_matched"]
            content = section["content"]
            if len(content) > self.settings.max_read_chars:
                base["content"] = content[: self.settings.max_read_chars]
                base["truncated"] = True
                base["next_action_hint"] = "章节超过 max_read_chars 已截断；可用更具体的子标题再 section，或用 snippets 检索关键词。"
            else:
                base["content"] = content
            return base
        if mode == "snippets":
            base["content"] = make_snippet(body, query or note["title"], self.settings.max_read_chars)
            return base
        if mode == "full":
            if len(body) > self.settings.max_read_chars and self.settings.full_over_limit_strategy == "strict":
                base["truncated"] = True
                base["next_action_hint"] = "Content exceeds max_read_chars. Read a specific section by heading."
                return base
            if self.settings.full_over_limit_strategy == "paged":
                pages = paginate_content(body, self.settings.max_read_chars)
                page_index = max(0, min(page - 1, len(pages) - 1))
                base["content"] = pages[page_index]
                base["page_info"] = {
                    "current": page_index + 1,
                    "total": len(pages),
                    "has_next": page_index < len(pages) - 1,
                    "has_prev": page_index > 0
                }
                return base
            if self.settings.full_over_limit_strategy == "compressed":
                base["content"] = compress_content(body, headings, self.settings.compressed_section_preview_chars)
                base["truncated"] = True
                return base
            base["content"] = body[: self.settings.max_read_chars]
            base["truncated"] = len(body) > self.settings.max_read_chars
            return base
        base["error"] = f"unsupported mode: {mode}"
        return base

    def _find_note(self, note_ref: str):
        if not self.settings.index_path.exists():
            return None
        conn = VaultIndex(self.settings.index_path, self.settings.vault_id).connect()
        try:
            row = conn.execute(
                "select * from notes where vault_id = ? and (note_id = ? or path = ?)",
                (self.settings.vault_id, note_ref, note_ref),
            ).fetchone()
            if row:
                return row
            return conn.execute(
                "select * from notes where vault_id = ? and path like ? order by length(path) limit 1",
                (self.settings.vault_id, f"%{note_ref}%"),
            ).fetchone()
        finally:
            conn.close()


CALLOUT_PREFIXES = (
    "> [!summary]",
    "> [!abstract]",
    "> [!tldr]",
    "> [!note]",
    "> [!info]",
    "> [!important]",
    "> [!tip]",
    "> [!warning]",
)


def extract_callouts(body: str) -> str:
    lines = body.splitlines()
    collected = []
    capture = False
    for line in lines:
        if any(line.startswith(prefix) for prefix in CALLOUT_PREFIXES):
            capture = True
            collected.append(line)
            continue
        if capture and line.startswith(">"):
            collected.append(line)
            continue
        capture = False
    return "\n".join(collected).strip()


def lead_paragraph(body: str) -> str:
    """返回首个标题前的前导段落；若无，则取首个非空、非标题段落。"""
    paragraphs = []
    current: list[str] = []
    for line in body.splitlines():
        if line.strip().startswith("#"):
            if current:
                break
            continue
        if not line.strip():
            if current:
                paragraphs.append("\n".join(current).strip())
                current = []
            continue
        current.append(line)
    if current:
        paragraphs.append("\n".join(current).strip())
    for para in paragraphs:
        if para:
            return para
    return ""


def extract_section(body: str, headings: list[dict], heading: str | None) -> str:
    return select_section(body, headings, heading)["content"]


def select_section(body: str, headings: list[dict], heading: str | None) -> dict:
    if not headings:
        if heading:
            return {
                "content": "",
                "heading": None,
                "heading_matched": False,
                "heading_not_found": True,
                "requested_heading": heading,
                "available_headings": [],
            }
        return {"content": body, "heading": None, "heading_matched": False}
    selected = None
    heading_matched = False
    if heading:
        for item in headings:
            if heading.lower() in item["title"].lower():
                selected = item
                heading_matched = True
                break
        if selected is None:
            return {
                "content": "",
                "heading": None,
                "heading_matched": False,
                "heading_not_found": True,
                "requested_heading": heading,
                "available_headings": compact_headings(headings),
            }
    if selected is None:
        selected = headings[0]
    lines = body.splitlines()
    return {
        "content": "\n".join(lines[selected["line_start"] - 1 : selected["line_end"]]).strip(),
        "heading": {
            "level": selected["level"],
            "title": selected["title"],
        },
        "heading_matched": heading_matched,
    }


def compact_headings(headings: list[dict]) -> list[dict]:
    return [heading for heading in headings if heading.get("level", 0) <= 3]


def paginate_content(body: str, page_size: int) -> list[str]:
    """Split content into pages at paragraph boundaries."""
    paragraphs = body.split("\n\n")
    pages = []
    current_page = []
    current_size = 0

    for para in paragraphs:
        para_size = len(para) + 2  # +2 for \n\n
        if current_size + para_size > page_size and current_page:
            pages.append("\n\n".join(current_page))
            current_page = [para]
            current_size = para_size
        else:
            current_page.append(para)
            current_size += para_size

    if current_page:
        pages.append("\n\n".join(current_page))

    return pages if pages else [""]


def compress_content(body: str, headings: list[dict], preview_chars: int) -> str:
    """Extract structural skeleton: all headings + preview of each section."""
    if not headings:
        # No headings, just return preview of entire body
        return body[:preview_chars]

    lines = body.splitlines()
    compressed_parts = []

    for i, heading in enumerate(headings):
        # Add the heading line
        heading_line = lines[heading["line_start"] - 1]
        compressed_parts.append(heading_line)

        # Extract content after heading, before next heading
        content_start = heading["line_start"]
        content_end = heading["line_end"]

        section_lines = lines[content_start:content_end]
        section_content = "\n".join(section_lines)

        # Take preview of section content
        if len(section_content) > preview_chars:
            preview = section_content[:preview_chars]
        else:
            preview = section_content

        if preview.strip():
            compressed_parts.append(preview)

    return "\n\n".join(compressed_parts)
