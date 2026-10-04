import json
import re
from pathlib import Path

from .config import VaultSettings
from .index import VaultIndex


FIELD_WEIGHTS = {
    "title": 100,
    "aliases": 80,
    "tags": 70,
    "path": 60,
    "headings": 50,
    "body": 10,
}

# 粗粒度 SQL 预过滤扫描的原始存储列（body 含标题行）。
_LIKE_COLUMNS = ("title", "path", "body", "tags_json", "aliases_json", "headings_json")

# SQL 预排序的元数据得分列（近似启发式：命中即计权重，仅供 LIMIT 前 Ranking；
# 最终排序仍由 Python 侧 _score_terms/_score_regex 重新打分）。
_META_SCORE_COLUMNS = (("title", 100), ("aliases_json", 80), ("tags_json", 70), ("path", 60), ("headings_json", 50))


def _meta_score_sql(terms: list[str] | None, regex_pattern: str | None = None) -> tuple[str, list]:
    """构造下推元数据得分表达式。返回 (SQL 表达式, 参数列表)。

    参数顺序即 SQL 文本中出现顺序，调用方必须把它放在 WHERE 参数之前绑定。
    """
    parts: list[str] = []
    params: list = []
    if terms is not None:
        for term in terms:
            for col, weight in _META_SCORE_COLUMNS:
                parts.append(f"case when {col} like ? escape '\\' then {weight} else 0 end")
                params.append(f"%{escape_like(term)}%")
    else:
        for col, weight in _META_SCORE_COLUMNS:
            parts.append(f"case when {col} regexp ? then {weight} else 0 end")
            params.append(regex_pattern)
    return " + ".join(parts), params


def escape_like(term: str) -> str:
    """转义 LIKE 通配符，使查询词按字面处理（配合 ESCAPE '\\'）。"""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _register_regexp(conn) -> None:
    def _regexp(pattern, value):
        if value is None:
            return False
        try:
            return re.search(pattern, value, re.IGNORECASE) is not None
        except re.error:
            return False

    conn.create_function("regexp", 2, _regexp)


def _decode_fields(note: dict) -> dict:
    """把一行 note 解码为「字段名 -> 小写文本」用于打分，以及原始 tags/aliases 列表。"""
    tags = json.loads(note["tags_json"])
    aliases = json.loads(note["aliases_json"])
    headings = json.loads(note["headings_json"])
    return {
        "fields": {
            "title": (note["title"] or "").lower(),
            "aliases": " ".join(aliases).lower(),
            "tags": " ".join(tags).lower(),
            "path": (note["path"] or "").lower(),
            "headings": " ".join(h["title"] for h in headings).lower(),
            "body": (note["body"] or "").lower(),
        },
        "tags": tags,
        "aliases": aliases,
    }


def _score_terms(fields: dict, terms: list[str]) -> tuple[int, list[str]]:
    """跨字段词覆盖：每个词取含它的最高权重字段；所有词都被覆盖才算命中。"""
    matched: set[str] = set()
    total = 0
    for term in terms:
        best_w = 0
        best_f = None
        for name, weight in FIELD_WEIGHTS.items():
            if term and term in fields[name] and weight > best_w:
                best_w = weight
                best_f = name
        if best_f is None:
            return 0, []
        total += best_w
        matched.add(best_f)
    return total, sorted(matched, key=lambda f: -FIELD_WEIGHTS[f])


def _score_regex(fields: dict, pattern: str) -> tuple[int, list[str]]:
    try:
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error:
        return 0, []
    matched = [name for name in FIELD_WEIGHTS if rx.search(fields[name])]
    if not matched:
        return 0, []
    total = sum(FIELD_WEIGHTS[name] for name in matched)
    return total, sorted(matched, key=lambda f: -FIELD_WEIGHTS[f])


class VaultSearch:
    FIELD_WEIGHTS = FIELD_WEIGHTS  # 向后兼容的类属性

    def __init__(self, settings: VaultSettings):
        self.settings = settings

    def discover(self, query: str, limit: int = 5, regex: bool = False) -> list[dict]:
        if not query or not query.strip() or not self.settings.index_path.exists():
            return []
        terms = query.lower().split()
        rows = self._fetch_regex_rows(query) if regex else self._fetch_plain_rows(terms)

        results = []
        for row in rows:
            note = dict(row)
            decoded = _decode_fields(note)
            if regex:
                score, matched = _score_regex(decoded["fields"], query)
            else:
                score, matched = _score_terms(decoded["fields"], terms)
            if score == 0:
                continue
            snippets = []
            if "body" in matched:
                snippet = make_snippet(note["body"], query, self.settings.max_discover_snippet_chars, regex)
                if snippet:
                    snippets = [snippet]
            results.append(
                {
                    "note_id": note["note_id"],
                    "path": note["path"],
                    "title": note["title"],
                    "tags": decoded["tags"],
                    "aliases": decoded["aliases"],
                    "score": score,
                    "matched_fields": matched,
                    "snippets": snippets,
                    "source_ref": f"{note['path']}#{note['title']}",
                }
            )
        results.sort(key=lambda item: (-item["score"], item["path"]))
        return results[:limit]

    def grep(self, query: str, limit: int = 5, regex: bool = False) -> list[dict]:
        if not query or not query.strip() or not self.settings.index_path.exists():
            return []
        if regex:
            try:
                re.compile(query)
            except re.error:
                return []
        scan_rows = self.settings.discover_scan_rows
        conn = VaultIndex(self.settings.index_path, self.settings.vault_id).connect()
        try:
            if regex:
                _register_regexp(conn)
                rows = conn.execute(
                    "select note_id, path, title, body from notes where vault_id = ? and body regexp ? order by path limit ?",
                    (self.settings.vault_id, query, scan_rows),
                ).fetchall()
            else:
                where = ["vault_id = ?"]
                params: list = [self.settings.vault_id]
                for term in query.lower().split():
                    where.append("body LIKE ? ESCAPE '\\'")
                    params.append(f"%{escape_like(term)}%")
                rows = conn.execute(
                    f"select note_id, path, title, body from notes where {' AND '.join(where)} order by path limit ?",
                    params + [scan_rows],
                ).fetchall()
        finally:
            conn.close()

        results = []
        for row in rows:
            results.append(
                {
                    "note_id": row["note_id"],
                    "path": row["path"],
                    "title": row["title"],
                    "snippet": make_snippet(row["body"], query, 500, regex),
                }
            )
        return results[:limit]

    def browse(self, folder: str = "", tag: str = "", limit: int = 50) -> list[dict]:
        """按目录前缀或精确标签列出笔记，无需关键词。"""
        if not self.settings.index_path.exists():
            return []
        where = ["vault_id = ?"]
        params: list = [self.settings.vault_id]
        folder = (folder or "").strip().strip("/")
        if folder:
            where.append("path like ? escape '\\'")
            params.append(f"{escape_like(folder)}/%")
        tag = (tag or "").strip()
        if tag:
            # tags_json 是 JSON 数组，带引号的精确元素匹配
            where.append("tags_json like ? escape '\\'")
            params.append(f'%"{escape_like(tag)}"%')
        sql = (
            "select note_id, path, title, tags_json from notes "
            f"where {' and '.join(where)} order by path limit ?"
        )
        params.append(max(1, limit))
        conn = VaultIndex(self.settings.index_path, self.settings.vault_id).connect()
        try:
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()
        return [
            {
                "note_id": row["note_id"],
                "path": row["path"],
                "title": row["title"],
                "tags": json.loads(row["tags_json"]),
            }
            for row in rows
        ]

    def _fetch_plain_rows(self, terms: list[str]):
        where = ["vault_id = ?"]
        params: list = [self.settings.vault_id]
        for term in terms:
            ors = " OR ".join(f"{col} LIKE ? ESCAPE '\\'" for col in _LIKE_COLUMNS)
            where.append(f"({ors})")
            params.extend([f"%{escape_like(term)}%"] * len(_LIKE_COLUMNS))
        score_expr, score_params = _meta_score_sql(terms=terms)
        sql = (
            "select note_id, path, title, tags_json, aliases_json, headings_json, body, "
            f"{score_expr} as meta_score "
            f"from notes where {' AND '.join(where)} order by meta_score desc, path limit ?"
        )
        # 参数按 SQL 文本顺序绑定：SELECT 里的 CASE WHEN 参数在 WHERE 参数之前
        conn = VaultIndex(self.settings.index_path, self.settings.vault_id).connect()
        try:
            return conn.execute(sql, score_params + params + [self.settings.discover_scan_rows]).fetchall()
        finally:
            conn.close()

    def _fetch_regex_rows(self, pattern: str):
        try:
            re.compile(pattern)
        except re.error:
            return []
        ors = " OR ".join(f"{col} REGEXP ?" for col in _LIKE_COLUMNS)
        score_expr, score_params = _meta_score_sql(terms=None, regex_pattern=pattern)
        sql = (
            "select note_id, path, title, tags_json, aliases_json, headings_json, body, "
            f"{score_expr} as meta_score "
            f"from notes where vault_id = ? and ({ors}) order by meta_score desc, path limit ?"
        )
        conn = VaultIndex(self.settings.index_path, self.settings.vault_id).connect()
        try:
            _register_regexp(conn)
            bind = score_params + [self.settings.vault_id] + [pattern] * len(_LIKE_COLUMNS) + [self.settings.discover_scan_rows]
            return conn.execute(sql, bind).fetchall()
        finally:
            conn.close()


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
        first = query.lower().split()
        needle = first[0] if first else ""
        index = text.lower().find(needle) if needle else 0
    if index < 0:
        index = 0
    start = max(0, index - max_chars // 3)
    end = min(len(text), start + max_chars)
    return text[start:end].strip()


def _resolve_vault_dirs(data_dir: Path, vault_id: str | None) -> list[Path]:
    """解析要搜索的 vault 目录列表,vault_id 不存在时抛出 ValueError。"""
    vaults_dir = Path(data_dir) / "vaults"
    if not vaults_dir.exists():
        return []
    if vault_id:
        vault_path = vaults_dir / vault_id
        if not vault_path.exists():
            available = [d.name for d in vaults_dir.iterdir() if d.is_dir()]
            raise ValueError(
                f"Knowledge vault '{vault_id}' not found. "
                f"Available vaults: {', '.join(available) if available else 'none'}"
            )
        return [vault_path]
    return [d for d in vaults_dir.iterdir() if d.is_dir()]


def search_across_vaults(data_dir: Path, query: str, limit: int = 5, regex: bool = False, vault_id: str | None = None, max_discover_snippet_chars: int | None = None) -> list[dict]:
    all_results = []
    for vault_dir in _resolve_vault_dirs(data_dir, vault_id):
        current_vault_id = vault_dir.name
        settings_kwargs = {"data_dir": data_dir, "vault_id": current_vault_id}
        if max_discover_snippet_chars is not None:
            settings_kwargs["max_discover_snippet_chars"] = max_discover_snippet_chars
        settings = VaultSettings(**settings_kwargs)
        if not settings.index_path.exists():
            continue
        results = VaultSearch(settings).discover(query, limit=limit * 2, regex=regex)
        for result in results:
            result["vault_id"] = current_vault_id
        all_results.extend(results)

    all_results.sort(key=lambda x: (-x["score"], x["path"]))
    return all_results[:limit]


def grep_across_vaults(data_dir: Path, query: str, limit: int = 5, regex: bool = False, vault_id: str | None = None) -> list[dict]:
    all_results = []
    for vault_dir in _resolve_vault_dirs(data_dir, vault_id):
        current_vault_id = vault_dir.name
        settings = VaultSettings(data_dir=data_dir, vault_id=current_vault_id)
        if not settings.index_path.exists():
            continue
        results = VaultSearch(settings).grep(query, limit=limit, regex=regex)
        for result in results:
            result["vault_id"] = current_vault_id
        all_results.extend(results)

    return all_results[:limit]
