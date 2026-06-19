import json
from pathlib import PurePosixPath

from .config import VaultSettings
from .index import VaultIndex


def _basename(path: str) -> str:
    name = PurePosixPath(path).name
    if name.lower().endswith(".md"):
        name = name[:-3]
    return name


def _target_keys(target: str) -> list[str]:
    """一个 wikilink target 可能写成 'note' 或 'folder/note'，按 basename 与全名解析。"""
    target = (target or "").strip()
    if not target:
        return []
    keys = {target.lower(), _basename(target).lower()}
    return [k for k in keys if k]


def find_related(settings: VaultSettings, note_id: str) -> dict:
    """在单库内解析给定 note 的 outlinks / backlinks。"""
    if not settings.index_path.exists():
        return {"found": False, "error": "note not found"}

    conn = VaultIndex(settings.index_path, settings.vault_id).connect()
    try:
        notes = conn.execute(
            "select note_id, path, title, aliases_json from notes where vault_id = ?",
            (settings.vault_id,),
        ).fetchall()
        links = conn.execute(
            "select l.note_id as src, l.target as target from links l "
            "join notes n on n.note_id = l.note_id where n.vault_id = ?",
            (settings.vault_id,),
        ).fetchall()
    finally:
        conn.close()

    by_id = {row["note_id"]: row for row in notes}
    if note_id not in by_id:
        return {"found": False, "error": "note not found"}

    # identifier(lower) -> note_id 解析表：basename + title + aliases
    resolver: dict[str, str] = {}
    for row in notes:
        for key in {_basename(row["path"]).lower(), (row["title"] or "").lower()}:
            if key:
                resolver.setdefault(key, row["note_id"])
        for alias in json.loads(row["aliases_json"]):
            if alias.strip():
                resolver.setdefault(alias.strip().lower(), row["note_id"])

    def _ref(nid: str) -> dict:
        row = by_id[nid]
        return {
            "ref": f"{settings.vault_id}:{nid}",
            "note_id": nid,
            "path": row["path"],
            "title": row["title"],
        }

    def _resolve(target: str) -> str | None:
        for key in _target_keys(target):
            if key in resolver:
                return resolver[key]
        return None

    outlinks = []
    seen_out: set[str] = set()
    for link in links:
        if link["src"] != note_id:
            continue
        resolved = _resolve(link["target"])
        if resolved and resolved != note_id:
            if resolved in seen_out:
                continue
            seen_out.add(resolved)
            outlinks.append({**_ref(resolved), "resolved": True})
        elif resolved is None:
            outlinks.append({"target": link["target"], "resolved": False})

    backlinks = []
    seen_back: set[str] = set()
    for link in links:
        if link["src"] == note_id:
            continue
        if _resolve(link["target"]) == note_id and link["src"] not in seen_back:
            seen_back.add(link["src"])
            backlinks.append(_ref(link["src"]))

    target = _ref(note_id)
    return {
        "found": True,
        "vault_id": settings.vault_id,
        "ref": target["ref"],
        "note_id": note_id,
        "path": target["path"],
        "title": target["title"],
        "outlinks": outlinks,
        "backlinks": backlinks,
    }
