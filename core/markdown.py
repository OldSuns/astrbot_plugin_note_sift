import json
import re
from dataclasses import dataclass, field


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)?(?:#([^\]|]+))?(?:\|([^\]]+))?\]\]")


@dataclass
class ParsedNote:
    title: str
    tags: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    headings: list[dict] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)
    body: str = ""
    frontmatter: dict = field(default_factory=dict)


def parse_markdown(text: str, fallback_title: str) -> ParsedNote:
    frontmatter, body = split_frontmatter(text)
    headings = extract_headings(body)
    links = extract_wikilinks(body)
    title = str(frontmatter.get("title") or "").strip()
    if not title and headings:
        title = headings[0]["title"]
    if not title:
        title = fallback_title
    return ParsedNote(
        title=title,
        tags=normalize_list(frontmatter.get("tags")),
        aliases=normalize_list(frontmatter.get("aliases")),
        headings=headings,
        links=links,
        body=body,
        frontmatter=frontmatter,
    )


def split_frontmatter(text: str) -> tuple[dict, str]:
    normalized = text.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        return {}, text
    end = normalized.find("\n---", 4)
    if end == -1:
        return {}, text
    raw = normalized[4:end]
    body = normalized[normalized.find("\n", end + 1) + 1 :]
    return parse_frontmatter(raw), body


def parse_frontmatter(raw: str) -> dict:
    try:
        import yaml

        loaded = yaml.safe_load(raw)
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return parse_frontmatter_fallback(raw)


def parse_frontmatter_fallback(raw: str) -> dict:
    result: dict[str, object] = {}
    current_key: str | None = None
    for line in raw.splitlines():
        if not line.strip():
            continue
        if line.startswith("  - ") and current_key:
            result.setdefault(current_key, [])
            if isinstance(result[current_key], list):
                result[current_key].append(line[4:].strip().strip('"\''))
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        current_key = key
        if value:
            result[key] = value.strip('"\'')
        else:
            result[key] = []
    return result


def normalize_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def extract_headings(body: str) -> list[dict]:
    lines = body.splitlines()
    headings: list[dict] = []
    for index, line in enumerate(lines, start=1):
        match = HEADING_RE.match(line)
        if not match:
            continue
        headings.append(
            {
                "level": len(match.group(1)),
                "title": match.group(2).strip(),
                "line_start": index,
                "line_end": len(lines),
            }
        )
    for index, heading in enumerate(headings):
        for next_heading in headings[index + 1 :]:
            if next_heading["level"] <= heading["level"]:
                heading["line_end"] = next_heading["line_start"] - 1
                break
    return headings


def extract_wikilinks(body: str) -> list[dict]:
    links = []
    for match in WIKILINK_RE.finditer(body):
        links.append(
            {
                "target": (match.group(1) or "").strip(),
                "heading": (match.group(2) or "").strip(),
                "alias": (match.group(3) or "").strip(),
                "raw": match.group(0),
            }
        )
    return links


def dumps_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
