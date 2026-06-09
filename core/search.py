import json
import re
from pathlib import Path

from .config import VaultSettings
from .index import VaultIndex


class VaultSearch:
    FIELD_WEIGHTS = {
        "title": 100,
        "aliases": 80,
        "tags": 70,
        "path": 60,
        "headings": 50,
        "body": 10,
    }

    def __init__(self, settings: VaultSettings):
        self.settings = settings

    def discover(self, query: str, limit: int = 5, regex: bool = False) -> list[dict]:
        rows = self._load_notes()
        results = []
        for row in rows:
            note = dict(row)
            tags = json.loads(note["tags_json"])
            aliases = json.loads(note["aliases_json"])
            headings = json.loads(note["headings_json"])
            fields = {
                "title": note["title"],
                "aliases": " ".join(aliases),
                "tags": " ".join(tags),
                "path": note["path"],
                "headings": " ".join(item["title"] for item in headings),
                "body": note["body"],
            }
            matched_fields = [name for name, value in fields.items() if matches(value, query, regex)]
            if not matched_fields:
                continue
            score = sum(self.FIELD_WEIGHTS[field] for field in matched_fields)
            snippets = []
            if matched_fields == ["body"] or (
                "body" in matched_fields
                and not any(field in matched_fields for field in ["title", "aliases", "tags", "path", "headings"])
            ):
                snippets = [make_snippet(note["body"], query, self.settings.max_discover_snippet_chars, regex)]
            results.append(
                {
                    "note_id": note["note_id"],
                    "path": note["path"],
                    "title": note["title"],
                    "tags": tags,
                    "aliases": aliases,
                    "score": score,
                    "matched_fields": matched_fields,
                    "snippets": [snippet for snippet in snippets if snippet],
                    "source_ref": f"{note['path']}#{note['title']}",
                }
            )
        return sorted(results, key=lambda item: item["score"], reverse=True)[:limit]

    def grep(self, query: str, limit: int = 5, regex: bool = False) -> list[dict]:
        results = []
        for row in self._load_notes():
            if matches(row["body"], query, regex):
                results.append(
                    {
                        "note_id": row["note_id"],
                        "path": row["path"],
                        "title": row["title"],
                        "snippet": make_snippet(row["body"], query, 500, regex),
                    }
                )
        return results[:limit]

    def _load_notes(self):
        conn = VaultIndex(self.settings.index_path, self.settings.vault_id).connect()
        try:
            return conn.execute("select * from notes where vault_id = ?", (self.settings.vault_id,)).fetchall()
        finally:
            conn.close()


def matches(value: str, query: str, regex: bool = False) -> bool:
    if not query:
        return False
    if regex:
        try:
            return re.search(query, value, re.IGNORECASE) is not None
        except re.error:
            return False
    # Plain search: all terms must be present
    value_lower = value.lower()
    terms = query.lower().split()
    return all(term in value_lower for term in terms)


def make_snippet(text: str, query: str, max_chars: int, regex: bool = False) -> str:
    if not text:
        return ""
    if regex:
        try:
            match = re.search(query, text, re.IGNORECASE)
        except re.error:
            match = None
        index = match.start() if match else 0
    else:
        index = text.lower().find(query.lower())
    if index < 0:
        index = 0
    start = max(0, index - max_chars // 3)
    end = min(len(text), start + max_chars)
    return text[start:end].strip()


def search_across_vaults(data_dir: Path, query: str, limit: int = 5, regex: bool = False, vault_id: str | None = None) -> list[dict]:
    """Search across multiple vaults or a specific vault.

    Args:
        data_dir: The data directory containing vaults
        query: Search query
        limit: Maximum results to return
        regex: Whether to use regex search
        vault_id: If specified, search only this vault; otherwise search all vaults

    Returns:
        List of search results with vault_id included
    """
    vaults_dir = Path(data_dir) / "vaults"
    if not vaults_dir.exists():
        return []

    all_results = []

    # Determine which vaults to search
    if vault_id:
        vault_path = vaults_dir / vault_id
        if not vault_path.exists():
            # List available vaults for helpful error message
            available = [d.name for d in vaults_dir.iterdir() if d.is_dir()] if vaults_dir.exists() else []
            raise ValueError(
                f"Knowledge vault '{vault_id}' not found. "
                f"Available vaults: {', '.join(available) if available else 'none'}"
            )
        vault_dirs = [vault_path]
    else:
        vault_dirs = [d for d in vaults_dir.iterdir() if d.is_dir()]

    for vault_dir in vault_dirs:
        current_vault_id = vault_dir.name
        settings = VaultSettings(data_dir=data_dir, vault_id=current_vault_id)

        if not settings.index_path.exists():
            continue

        searcher = VaultSearch(settings)
        results = searcher.discover(query, limit=limit * 2, regex=regex)  # Get more to merge

        # Add vault_id to each result
        for result in results:
            result["vault_id"] = current_vault_id

        all_results.extend(results)

    # Sort by score and limit
    all_results.sort(key=lambda x: x["score"], reverse=True)
    return all_results[:limit]
