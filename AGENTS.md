# Agent Notes

## Project Shape
- This is an AstrBot plugin, not a standalone app. `main.py` registers `NoteSiftPlugin` and wires AstrBot commands/tools to the `core/` modules.
- `core/importer.py` owns zip import, Obsidian vault-root detection, safe extraction, and index rebuilds.
- `core/index.py` owns the SQLite schema and stable note IDs; `core/search.py` and `core/reader.py` read from that index.
- Runtime plugin data lives under `AstrBot data/plugin_data/astrbot_plugin_note_sift/`; if AstrBot path APIs are unavailable it falls back to local `data/`.

## Commands
- Install the only declared runtime dependency with `python -m pip install -r requirements.txt`.
- Run all tests with `python -m pytest` from the repo root.
- Run one test file with `python -m pytest tests/test_core.py`.
- Run one test with `python -m pytest tests/test_core.py::CoreTest::test_import_extracts_markdown_indexes_metadata_and_deletes_zip`.
- Do not run multiple full test commands concurrently: tests share `tests/.tmp` and `tests/.tmp_rebuild`, which can collide on Windows.

## Testing Notes
- Tests are `unittest` classes but are pytest-compatible; there is no pytest config, lint config, or typecheck config in this repo.
- `tests/test_plugin_import.py` stubs AstrBot modules, so core changes can be tested without installing AstrBot.
- Importer tests intentionally delete imported zip files; create disposable zips in temp dirs only.

## Behavior To Preserve
- Zip extraction only keeps `.md`, `.markdown`, and `.txt` files, rejects unsafe paths, ignores files over `VaultSettings.max_file_size_mb`, and deletes the zip after a successful import.
- If a zip contains `.obsidian`, only files under that detected vault root are imported and the root prefix is stripped.
- Plain search requires all query terms to be present; regex search is only exposed via LLM tools, not slash commands.
- Slash-command `/kb search` searches one vault via `vault_id:query`; LLM `kb_discover` searches across all vaults when `vault_id` is empty.
- `full_over_limit_strategy` controls long reads: `strict` returns headings only, `paged` splits on paragraph boundaries, and `compressed` returns headings plus per-section previews.

## Docs And Config
- `_conf_schema.json` is the AstrBot configuration source of truth for exposed settings.
- `metadata.yaml` carries plugin marketplace metadata, including the AstrBot version constraint.
- Keep README/docs command descriptions in sync with `main.py` command signatures and actual tool behavior.
