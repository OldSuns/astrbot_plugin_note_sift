import hashlib
import sqlite3
from pathlib import Path

from .markdown import ParsedNote, dumps_json


SCHEMA = """
create table if not exists vaults(
  vault_id text primary key,
  name text not null,
  root_path text not null,
  created_at text default current_timestamp,
  updated_at text default current_timestamp
);
create table if not exists imports(
  import_id text primary key,
  vault_id text not null,
  zip_hash text not null,
  imported_at text default current_timestamp,
  file_count integer not null,
  ignored_count integer not null,
  status text not null
);
create table if not exists notes(
  note_id text primary key,
  vault_id text not null,
  path text not null,
  title text not null,
  aliases_json text not null,
  tags_json text not null,
  headings_json text not null,
  frontmatter_json text not null,
  mtime real not null,
  size integer not null,
  content_hash text not null,
  body text not null
);
create table if not exists links(
  id integer primary key autoincrement,
  note_id text not null,
  target text not null,
  alias text not null,
  heading text not null,
  raw text not null
);
"""


def stable_note_id(vault_id: str, relative_path: str) -> str:
    return hashlib.sha1(f"{vault_id}:{relative_path}".encode("utf-8")).hexdigest()[:16]


class VaultIndex:
    def __init__(self, db_path: Path, vault_id: str):
        self.db_path = db_path
        self.vault_id = vault_id

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA)
        return conn

    def initialize(self, root_path: Path) -> None:
        conn = self.connect()
        try:
            conn.execute(
                "insert or replace into vaults(vault_id, name, root_path, updated_at) values(?, ?, ?, current_timestamp)",
                (self.vault_id, self.vault_id, str(root_path)),
            )
            conn.commit()
        finally:
            conn.close()

    def rebuild_notes(self, root_path: Path, notes: list[tuple[str, Path, ParsedNote]]) -> None:
        conn = self.connect()
        try:
            conn.execute("delete from notes where vault_id = ?", (self.vault_id,))
            conn.execute("delete from links where note_id not in (select note_id from notes)")
            conn.execute(
                "insert or replace into vaults(vault_id, name, root_path, updated_at) values(?, ?, ?, current_timestamp)",
                (self.vault_id, self.vault_id, str(root_path)),
            )
            for relative_path, file_path, parsed in notes:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                note_id = stable_note_id(self.vault_id, relative_path)
                stat = file_path.stat()
                conn.execute(
                    """
                    insert into notes(note_id, vault_id, path, title, aliases_json, tags_json, headings_json, frontmatter_json, mtime, size, content_hash, body)
                    values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        note_id,
                        self.vault_id,
                        relative_path,
                        parsed.title,
                        dumps_json(parsed.aliases),
                        dumps_json(parsed.tags),
                        dumps_json(parsed.headings),
                        dumps_json(parsed.frontmatter),
                        stat.st_mtime,
                        stat.st_size,
                        hashlib.sha1(content.encode("utf-8", errors="ignore")).hexdigest(),
                        parsed.body,
                    ),
                )
                for link in parsed.links:
                    conn.execute(
                        "insert into links(note_id, target, alias, heading, raw) values(?, ?, ?, ?, ?)",
                        (note_id, link["target"], link["alias"], link["heading"], link["raw"]),
                    )
            conn.commit()
        finally:
            conn.close()
