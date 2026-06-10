import shutil
import sqlite3
import sys
import unittest
import zipfile
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import VaultSettings
from core.importer import ImportErrorInfo, VaultImporter
from core.reader import VaultReader
from core.search import VaultSearch


def write_zip(path: Path, files: dict[str, str | bytes]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)


class CoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp_path = Path(__file__).parent / ".tmp"
        if self.tmp_path.exists():
            shutil.rmtree(self.tmp_path)
        self.tmp_path.mkdir(parents=True)

    def tearDown(self):
        if self.tmp_path.exists():
            shutil.rmtree(self.tmp_path)

    def test_import_rejects_path_traversal_and_keeps_previous_vault(self):
        data_dir = self.tmp_path / "data"
        settings = VaultSettings(data_dir=data_dir)
        importer = VaultImporter(settings)

        good_zip = self.tmp_path / "good.zip"
        write_zip(good_zip, {"note.md": "# Safe\n\nhello"})
        importer.import_zip(good_zip)

        bad_zip = self.tmp_path / "bad.zip"
        write_zip(bad_zip, {"../evil.md": "owned"})

        with self.assertRaisesRegex(ImportErrorInfo, "unsafe path"):
            importer.import_zip(bad_zip)

        self.assertTrue((data_dir / "vaults" / "default" / "files" / "note.md").exists())
        self.assertFalse((self.tmp_path / "evil.md").exists())

    def test_import_extracts_markdown_indexes_metadata_and_deletes_zip(self):
        zip_path = self.tmp_path / "vault.zip"
        write_zip(
            zip_path,
            {
                "儿科学/川崎病.md": "---\ntags:\n  - 儿科学\naliases:\n  - KD\n---\n\n# 川崎病\n\n> [!summary] IVIG 是核心治疗。\n\n## 治疗\n阿司匹林。\n[[../心血管|心血管]]",
                "image.png": b"not kept",
            },
        )
        settings = VaultSettings(data_dir=self.tmp_path / "data")

        manifest = VaultImporter(settings).import_zip(zip_path)

        self.assertEqual(manifest.file_count, 1)
        self.assertEqual(manifest.ignored_count, 1)
        self.assertTrue(manifest.imported_at)
        self.assertFalse(zip_path.exists())
        self.assertTrue((settings.vault_dir / "files" / "儿科学" / "川崎病.md").exists())
        self.assertFalse((settings.vault_dir / "files" / "image.png").exists())
        manifest_data = json.loads(settings.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest_data["imported_at"], manifest.imported_at)

        db = sqlite3.connect(settings.index_path)
        try:
            row = db.execute("select path, title, tags_json, aliases_json from notes").fetchone()
        finally:
            db.close()
        self.assertEqual(row[0], "儿科学/川崎病.md")
        self.assertEqual(row[1], "川崎病")
        self.assertIn("儿科学", row[2])
        self.assertIn("KD", row[3])

    def test_search_discloses_metadata_first_and_body_snippet_only_for_body_hits(self):
        zip_path = self.tmp_path / "vault.zip"
        write_zip(
            zip_path,
            {
                "儿科学/川崎病.md": "---\ntags:\n  - 儿科学\naliases:\n  - KD\n---\n\n# 川崎病\n\n## 治疗\nIVIG 是核心治疗。",
                "口腔医学/麻醉.md": "# 口腔麻醉\n\n局麻并发症包括晕厥。",
            },
        )
        settings = VaultSettings(data_dir=self.tmp_path / "data")
        VaultImporter(settings).import_zip(zip_path)

        search = VaultSearch(settings)
        title_hit = search.discover("川崎病", limit=5)
        self.assertEqual(title_hit[0]["title"], "川崎病")
        self.assertIn("title", title_hit[0]["matched_fields"])
        self.assertEqual(title_hit[0]["snippets"], [])

        body_hit = search.discover("晕厥", limit=5)
        self.assertEqual(body_hit[0]["title"], "口腔麻醉")
        self.assertIn("body", body_hit[0]["matched_fields"])
        self.assertTrue(body_hit[0]["snippets"])

    def test_reader_strict_full_over_limit_returns_heading_tree(self):
        zip_path = self.tmp_path / "vault.zip"
        write_zip(
            zip_path,
            {"long.md": "# Long\n\n## A\n" + "x" * 200 + "\n\n## B\n" + "y" * 200},
        )
        settings = VaultSettings(data_dir=self.tmp_path / "data", max_read_chars=80)
        VaultImporter(settings).import_zip(zip_path)

        reader = VaultReader(settings)
        result = reader.read_note("long.md", mode="full")

        self.assertTrue(result["truncated"])
        self.assertEqual(result["content"], "")
        self.assertEqual([heading["title"] for heading in result["headings"]], ["Long", "A", "B"])
        self.assertTrue(result["next_action_hint"])

    def test_import_uses_obsidian_directory_as_vault_root(self):
        zip_path = self.tmp_path / "vault.zip"
        write_zip(
            zip_path,
            {
                "outer/readme.md": "# Outside",
                "wrapped/.obsidian/app.json": "{}",
                "wrapped/学科/笔记.md": "# Inner\n\n正文",
            },
        )
        settings = VaultSettings(data_dir=self.tmp_path / "data")

        manifest = VaultImporter(settings).import_zip(zip_path)

        self.assertEqual(manifest.file_count, 1)
        self.assertEqual(manifest.vault_root, "wrapped")
        self.assertTrue((settings.files_dir / "学科" / "笔记.md").exists())
        self.assertFalse((settings.files_dir / "outer" / "readme.md").exists())

    def test_reader_section_and_snippets_modes_are_specific(self):
        zip_path = self.tmp_path / "vault.zip"
        write_zip(
            zip_path,
            {
                "note.md": "# Root\n\nintro\n\n## Alpha\nalpha body\n\n## Beta\nbeta keyword body\n",
            },
        )
        settings = VaultSettings(data_dir=self.tmp_path / "data")
        VaultImporter(settings).import_zip(zip_path)

        reader = VaultReader(settings)
        section = reader.read_note("note.md", mode="section", heading="Beta")
        snippets = reader.read_note("note.md", mode="snippets", query="keyword")

        self.assertIn("## Beta", section["content"])
        self.assertIn("beta keyword body", section["content"])
        self.assertNotIn("alpha body", section["content"])
        self.assertIn("keyword", snippets["content"])

    def test_discover_requires_all_query_terms_for_plain_search(self):
        zip_path = self.tmp_path / "vault.zip"
        write_zip(
            zip_path,
            {
                "a.md": "# 川崎病\n\nIVIG 治疗",
                "b.md": "# 川崎病\n\n阿司匹林 治疗",
            },
        )
        settings = VaultSettings(data_dir=self.tmp_path / "data")
        VaultImporter(settings).import_zip(zip_path)

        results = VaultSearch(settings).discover("川崎病 IVIG", limit=5)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["path"], "a.md")

    def test_paged_mode_returns_first_page_with_page_info(self):
        zip_path = self.tmp_path / "vault.zip"
        # Create content larger than page size
        long_content = "# Long Note\n\n"
        for i in range(10):
            long_content += f"Paragraph {i}. " + ("x" * 100) + "\n\n"
        write_zip(zip_path, {"long.md": long_content})

        settings = VaultSettings(
            data_dir=self.tmp_path / "data",
            max_read_chars=300,
            full_over_limit_strategy="paged"
        )
        VaultImporter(settings).import_zip(zip_path)

        reader = VaultReader(settings)
        result = reader.read_note("long.md", mode="full", page=1)

        self.assertTrue(result["found"])
        self.assertIn("page_info", result)
        self.assertEqual(result["page_info"]["current"], 1)
        self.assertTrue(result["page_info"]["total"] > 1)
        self.assertTrue(result["page_info"]["has_next"])
        self.assertFalse(result["page_info"]["has_prev"])
        self.assertTrue(len(result["content"]) <= 300)

    def test_paged_mode_navigates_to_second_page(self):
        zip_path = self.tmp_path / "vault.zip"
        long_content = "# Long Note\n\n"
        for i in range(10):
            long_content += f"Paragraph {i}. " + ("x" * 100) + "\n\n"
        write_zip(zip_path, {"long.md": long_content})

        settings = VaultSettings(
            data_dir=self.tmp_path / "data",
            max_read_chars=300,
            full_over_limit_strategy="paged"
        )
        VaultImporter(settings).import_zip(zip_path)

        reader = VaultReader(settings)
        result = reader.read_note("long.md", mode="full", page=2)

        self.assertTrue(result["found"])
        self.assertEqual(result["page_info"]["current"], 2)
        self.assertTrue(result["page_info"]["has_prev"])
        self.assertIn("Paragraph", result["content"])

    def test_compressed_mode_returns_headings_with_section_previews(self):
        zip_path = self.tmp_path / "vault.zip"
        content = """# Main Title

Intro paragraph with some text.

## Section A

This is section A with a lot of content. """ + ("x" * 300) + """

## Section B

This is section B with different content. """ + ("y" * 300)
        write_zip(zip_path, {"doc.md": content})

        settings = VaultSettings(
            data_dir=self.tmp_path / "data",
            max_read_chars=100,
            full_over_limit_strategy="compressed",
            compressed_section_preview_chars=50
        )
        VaultImporter(settings).import_zip(zip_path)

        reader = VaultReader(settings)
        result = reader.read_note("doc.md", mode="full")

        self.assertTrue(result["found"])
        self.assertTrue(result["truncated"])
        self.assertIn("# Main Title", result["content"])
        self.assertIn("## Section A", result["content"])
        self.assertIn("## Section B", result["content"])
        # Should include preview of each section
        self.assertIn("This is section A", result["content"])
        self.assertIn("This is section B", result["content"])
        # Should NOT include all the x's and y's
        self.assertTrue(len(result["content"]) < len(content))

    def test_paged_mode_with_short_content_returns_single_page(self):
        zip_path = self.tmp_path / "vault.zip"
        short_content = "# Short\n\nThis is short."
        write_zip(zip_path, {"short.md": short_content})

        settings = VaultSettings(
            data_dir=self.tmp_path / "data",
            max_read_chars=1000,
            full_over_limit_strategy="paged"
        )
        VaultImporter(settings).import_zip(zip_path)

        reader = VaultReader(settings)
        result = reader.read_note("short.md", mode="full")

        self.assertTrue(result["found"])
        self.assertIn("page_info", result)
        self.assertEqual(result["page_info"]["total"], 1)
        self.assertFalse(result["page_info"]["has_next"])
        self.assertFalse(result["page_info"]["has_prev"])
        self.assertEqual(result["content"], short_content)

    def test_extract_vault_id_from_zip_filename(self):
        from core.importer import extract_vault_id_from_path

        self.assertEqual(extract_vault_id_from_path(Path("medical_vault.zip")), "medical_vault")
        self.assertEqual(extract_vault_id_from_path(Path("儿科学-2024.zip")), "儿科学_2024")
        self.assertEqual(extract_vault_id_from_path(Path("/path/to/my-notes.zip")), "my_notes")
        self.assertEqual(extract_vault_id_from_path(Path("simple.zip")), "simple")

    def test_import_multiple_vaults_with_different_ids(self):
        medical_zip = self.tmp_path / "medical.zip"
        write_zip(medical_zip, {"cardiology.md": "# 心脏病学\n\n心血管疾病"})

        tech_zip = self.tmp_path / "tech_notes.zip"
        write_zip(tech_zip, {"python.md": "# Python\n\nProgramming language"})

        data_dir = self.tmp_path / "data"

        # Import first vault
        settings1 = VaultSettings(data_dir=data_dir, vault_id="medical")
        manifest1 = VaultImporter(settings1).import_zip(medical_zip)
        self.assertEqual(manifest1.vault_id, "medical")
        self.assertEqual(manifest1.file_count, 1)

        # Import second vault
        settings2 = VaultSettings(data_dir=data_dir, vault_id="tech_notes")
        manifest2 = VaultImporter(settings2).import_zip(tech_zip)
        self.assertEqual(manifest2.vault_id, "tech_notes")
        self.assertEqual(manifest2.file_count, 1)

        # Verify both vaults exist independently
        self.assertTrue((data_dir / "vaults" / "medical" / "files" / "cardiology.md").exists())
        self.assertTrue((data_dir / "vaults" / "tech_notes" / "files" / "python.md").exists())

    def test_search_across_multiple_vaults(self):
        from core.search import search_across_vaults

        medical_zip = self.tmp_path / "medical.zip"
        write_zip(medical_zip, {"cardiology.md": "# 心脏病学\n\n心血管疾病"})

        tech_zip = self.tmp_path / "tech.zip"
        write_zip(tech_zip, {"python.md": "# Python\n\nProgramming"})

        data_dir = self.tmp_path / "data"
        VaultImporter(VaultSettings(data_dir=data_dir, vault_id="medical")).import_zip(medical_zip)
        VaultImporter(VaultSettings(data_dir=data_dir, vault_id="tech")).import_zip(tech_zip)

        # Search across all vaults
        results = search_across_vaults(data_dir, "Python", limit=5)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Python")
        self.assertEqual(results[0]["vault_id"], "tech")


if __name__ == "__main__":
    unittest.main()
