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
            base["content"] = extract_callouts(body)
            return base
        if mode == "section":
            base["content"] = extract_section(body, headings, heading)
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


def extract_callouts(body: str) -> str:
    lines = body.splitlines()
    collected = []
    capture = False
    for line in lines:
        if line.startswith("> [!summary]") or line.startswith("> [!warning]") or line.startswith("> [!tip]"):
            capture = True
            collected.append(line)
            continue
        if capture and line.startswith(">"):
            collected.append(line)
            continue
        capture = False
    return "\n".join(collected).strip()


def extract_section(body: str, headings: list[dict], heading: str | None) -> str:
    if not headings:
        return body
    selected = None
    if heading:
        for item in headings:
            if heading.lower() in item["title"].lower():
                selected = item
                break
    if selected is None:
        selected = headings[0]
    lines = body.splitlines()
    return "\n".join(lines[selected["line_start"] - 1 : selected["line_end"]]).strip()


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
