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
from core.search import VaultSearch, grep_across_vaults


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

    def test_reader_missing_index_does_not_create_default_vault(self):
        data_dir = self.tmp_path / "data"
        settings = VaultSettings(data_dir=data_dir)

        result = VaultReader(settings).read_note("missing.md", mode="outline")

        self.assertFalse(result["found"])
        self.assertFalse((data_dir / "vaults" / "default").exists())

    def test_search_missing_index_does_not_create_default_vault(self):
        data_dir = self.tmp_path / "data"
        settings = VaultSettings(data_dir=data_dir)

        results = VaultSearch(settings).grep("missing", limit=5)

        self.assertEqual(results, [])
        self.assertFalse((data_dir / "vaults" / "default").exists())

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

    def test_grep_across_multiple_vaults_without_default(self):
        medical_zip = self.tmp_path / "medical.zip"
        write_zip(medical_zip, {"cardiology.md": "# 心脏病学\n\n心血管疾病"})

        tech_zip = self.tmp_path / "tech.zip"
        write_zip(tech_zip, {"python.md": "# Python\n\nProgramming"})

        data_dir = self.tmp_path / "data"
        VaultImporter(VaultSettings(data_dir=data_dir, vault_id="medical")).import_zip(medical_zip)
        VaultImporter(VaultSettings(data_dir=data_dir, vault_id="tech")).import_zip(tech_zip)

        results = grep_across_vaults(data_dir, "Programming", limit=5)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Python")
        self.assertEqual(results[0]["vault_id"], "tech")
        self.assertFalse((data_dir / "vaults" / "default").exists())

    def test_index_has_no_fts_or_headings_tables(self):
        zip_path = self.tmp_path / "vault.zip"
        write_zip(zip_path, {"a.md": "# A\n\n## H\nbody"})
        settings = VaultSettings(data_dir=self.tmp_path / "data")
        VaultImporter(settings).import_zip(zip_path)

        db = sqlite3.connect(settings.index_path)
        try:
            names = {r[0] for r in db.execute("select name from sqlite_master where type in ('table','view')").fetchall()}
        finally:
            db.close()
        self.assertNotIn("notes_fts", names)
        self.assertNotIn("headings", names)
        self.assertIn("notes", names)
        self.assertIn("links", names)

    def test_discover_cross_field_term_coverage(self):
        zip_path = self.tmp_path / "vault.zip"
        write_zip(
            zip_path,
            {
                # title 来自 frontmatter（不出现在 body），诊断 只在 body —— 两词分处不同字段
                "a.md": "---\ntitle: 川崎病\naliases:\n  - KD\n---\n\n诊断标准与 IVIG",
                "b.md": "---\ntitle: 普通感冒\n---\n\n川崎相关但无该词条",
            },
        )
        settings = VaultSettings(data_dir=self.tmp_path / "data")
        VaultImporter(settings).import_zip(zip_path)

        # "川崎病" 在 title、"诊断" 在 body —— 分处不同字段也应命中（旧逻辑要求同字段，会漏）
        results = VaultSearch(settings).discover("川崎病 诊断", limit=5)
        self.assertEqual([r["path"] for r in results], ["a.md"])
        # 别名命中
        alias_hit = VaultSearch(settings).discover("KD", limit=5)
        self.assertEqual(alias_hit[0]["path"], "a.md")
        self.assertIn("aliases", alias_hit[0]["matched_fields"])

    def test_discover_escapes_like_wildcards(self):
        zip_path = self.tmp_path / "vault.zip"
        write_zip(zip_path, {"u.md": "# Underscore\n\nkb_read 是工具", "x.md": "# Other\n\nkbXread 不应被当作匹配"})
        settings = VaultSettings(data_dir=self.tmp_path / "data")
        VaultImporter(settings).import_zip(zip_path)

        results = VaultSearch(settings).discover("kb_read", limit=5)
        paths = {r["path"] for r in results}
        self.assertIn("u.md", paths)
        self.assertNotIn("x.md", paths)

    def test_discover_regex_via_sql_function(self):
        zip_path = self.tmp_path / "vault.zip"
        write_zip(zip_path, {"a.md": "# 阿司匹林\n\n剂量 80mg", "b.md": "# 布洛芬\n\n无关"})
        settings = VaultSettings(data_dir=self.tmp_path / "data")
        VaultImporter(settings).import_zip(zip_path)

        results = VaultSearch(settings).discover(r"\d+mg", limit=5, regex=True)
        self.assertEqual([r["path"] for r in results], ["a.md"])
        # 非法正则安全返回空
        self.assertEqual(VaultSearch(settings).discover("(", limit=5, regex=True), [])

    def test_summary_falls_back_to_lead_paragraph_when_no_callout(self):
        zip_path = self.tmp_path / "vault.zip"
        write_zip(zip_path, {"n.md": "# 标题\n\n这是前导段落，应作为摘要。\n\n## 章节\n正文"})
        settings = VaultSettings(data_dir=self.tmp_path / "data")
        VaultImporter(settings).import_zip(zip_path)

        result = VaultReader(settings).read_note("n.md", mode="summary")
        self.assertTrue(result["found"])
        self.assertIn("前导段落", result["content"])
        self.assertTrue(result["next_action_hint"])

    def test_summary_extracts_extended_callouts(self):
        zip_path = self.tmp_path / "vault.zip"
        write_zip(zip_path, {"n.md": "# T\n\n> [!note] 重点提示\n\n正文"})
        settings = VaultSettings(data_dir=self.tmp_path / "data")
        VaultImporter(settings).import_zip(zip_path)

        result = VaultReader(settings).read_note("n.md", mode="summary")
        self.assertIn("重点提示", result["content"])

    def test_section_truncates_when_over_max_read_chars(self):
        zip_path = self.tmp_path / "vault.zip"
        write_zip(zip_path, {"n.md": "# 标题\n\n## 大节\n" + "x" * 500})
        settings = VaultSettings(data_dir=self.tmp_path / "data", max_read_chars=100)
        VaultImporter(settings).import_zip(zip_path)

        result = VaultReader(settings).read_note("n.md", mode="section", heading="大节")
        self.assertTrue(result["heading_matched"])
        self.assertEqual(result["heading"]["title"], "大节")
        self.assertTrue(result["truncated"])
        self.assertLessEqual(len(result["content"]), 100)
        self.assertTrue(result["next_action_hint"])

    def test_section_not_truncated_when_within_limit(self):
        zip_path = self.tmp_path / "vault.zip"
        write_zip(zip_path, {"n.md": "# 标题\n\n## 小节\n短内容"})
        settings = VaultSettings(data_dir=self.tmp_path / "data", max_read_chars=8000)
        VaultImporter(settings).import_zip(zip_path)

        result = VaultReader(settings).read_note("n.md", mode="section", heading="小节")
        self.assertFalse(result["truncated"])
        self.assertIn("短内容", result["content"])

    def test_search_across_vaults_honors_snippet_chars(self):
        from core.search import search_across_vaults

        zip_path = self.tmp_path / "v.zip"
        write_zip(zip_path, {"c.md": "# 心脏\n\n" + ("心血管疾病的相关论述。" * 200)})
        data_dir = self.tmp_path / "data"
        VaultImporter(VaultSettings(data_dir=data_dir, vault_id="v")).import_zip(zip_path)

        short = search_across_vaults(data_dir, "心血管疾病", limit=5, max_discover_snippet_chars=50)
        long = search_across_vaults(data_dir, "心血管疾病", limit=5, max_discover_snippet_chars=400)

        self.assertTrue(short[0]["snippets"])
        self.assertLessEqual(len(short[0]["snippets"][0]), 50)
        self.assertGreater(len(long[0]["snippets"][0]), 50)


    def test_grep_regex_search(self):
        zip_path = self.tmp_path / "vault.zip"
        write_zip(zip_path, {"a.md": "# 笔记\n\n剂量 80mg 每日", "b.md": "# 其他\n\n无数字"})
        settings = VaultSettings(data_dir=self.tmp_path / "data")
        VaultImporter(settings).import_zip(zip_path)

        results = VaultSearch(settings).grep(r"\d+mg", limit=5, regex=True)
        self.assertEqual([r["path"] for r in results], ["a.md"])
        self.assertIn("80mg", results[0]["snippet"])
        # 非法正则安全返回空
        self.assertEqual(VaultSearch(settings).grep("(", limit=5, regex=True), [])

    def test_make_snippet_regex_mode(self):
        from core.search import make_snippet

        text = "前文剂量 80mg 后文"
        snippet = make_snippet(text, r"\d+mg", 20, regex=True)
        self.assertIn("80mg", snippet)

    def test_search_across_vaults_invalid_vault_raises(self):
        from core.search import search_across_vaults

        data_dir = self.tmp_path / "data"
        zip_path = self.tmp_path / "v.zip"
        write_zip(zip_path, {"a.md": "# A\n\nbody"})
        VaultImporter(VaultSettings(data_dir=data_dir, vault_id="real")).import_zip(zip_path)

        with self.assertRaisesRegex(ValueError, "not found"):
            search_across_vaults(data_dir, "body", limit=5, vault_id="ghost")

    def test_grep_across_vaults_invalid_vault_raises(self):
        from core.search import grep_across_vaults

        data_dir = self.tmp_path / "data"
        zip_path = self.tmp_path / "v.zip"
        write_zip(zip_path, {"a.md": "# A\n\nbody"})
        VaultImporter(VaultSettings(data_dir=data_dir, vault_id="real")).import_zip(zip_path)

        with self.assertRaisesRegex(ValueError, "not found"):
            grep_across_vaults(data_dir, "body", limit=5, vault_id="ghost")

    def test_resolve_read_target_ambiguous_across_vaults(self):
        """跨库同名 note 应返回 ambiguous 候选,而非静默选一个。"""
        zip_path = self.tmp_path / "v.zip"
        write_zip(zip_path, {"同名.md": "# 同名笔记\n\n内容"})
        data_dir = self.tmp_path / "data"
        VaultImporter(VaultSettings(data_dir=data_dir, vault_id="v1")).import_zip(zip_path)
        # 重新创建 zip 再导入第二个库
        write_zip(zip_path, {"同名.md": "# 同名笔记\n\n内容"})
        VaultImporter(VaultSettings(data_dir=data_dir, vault_id="v2")).import_zip(zip_path)

        # 模拟 _resolve_read_target 的跨库解析逻辑
        from core.reader import VaultReader
        matches = []
        for vault_dir in sorted((data_dir / "vaults").iterdir()):
            if not vault_dir.is_dir():
                continue
            settings = VaultSettings(data_dir=data_dir, vault_id=vault_dir.name)
            if not settings.index_path.exists():
                continue
            found = VaultReader(settings).read_note("同名.md", mode="outline")
            if found.get("found"):
                matches.append({"vault_id": vault_dir.name, "note_id": found["note_id"]})

        self.assertEqual(len(matches), 2)
        vault_ids = {m["vault_id"] for m in matches}
        self.assertEqual(vault_ids, {"v1", "v2"})

    def test_resolve_read_target_unique_note_no_ambiguity(self):
        """只有一个库含该 note 时,不应产生歧义。"""
        zip_path = self.tmp_path / "v.zip"
        write_zip(zip_path, {"独有.md": "# 独有笔记\n\n内容"})
        data_dir = self.tmp_path / "data"
        VaultImporter(VaultSettings(data_dir=data_dir, vault_id="v1")).import_zip(zip_path)

        from core.reader import VaultReader
        settings = VaultSettings(data_dir=data_dir, vault_id="v1")
        found = VaultReader(settings).read_note("独有.md", mode="outline")
        self.assertTrue(found["found"])

    def test_links_no_self_loop(self):
        """自链笔记不应出现在 outlinks 中。"""
        zip_path = self.tmp_path / "v.zip"
        write_zip(zip_path, {"a.md": "# A\n\n自链 [[A]] 和 [[B]]", "b.md": "# B\n\n内容"})
        settings = VaultSettings(data_dir=self.tmp_path / "data")
        VaultImporter(settings).import_zip(zip_path)

        from core.index import stable_note_id
        from core.links import find_related

        a_id = stable_note_id("default", "a.md")
        related = find_related(settings, a_id)
        out_ids = {o.get("note_id") for o in related["outlinks"] if o.get("note_id")}
        self.assertNotIn(a_id, out_ids)

    def test_links_dedup_outlinks(self):
        """同一目标被多次链接时,outlinks 去重。"""
        zip_path = self.tmp_path / "v.zip"
        write_zip(zip_path, {"a.md": "# A\n\n[[B]] 再次 [[B]]", "b.md": "# B\n\n内容"})
        settings = VaultSettings(data_dir=self.tmp_path / "data")
        VaultImporter(settings).import_zip(zip_path)

        from core.index import stable_note_id
        from core.links import find_related

        a_id = stable_note_id("default", "a.md")
        related = find_related(settings, a_id)
        resolved_out = [o for o in related["outlinks"] if o.get("resolved")]
        self.assertEqual(len(resolved_out), 1)


    def test_rebuild_ignores_oversized_files(self):
        """rebuild_from_files 应跳过超大文件并统计 ignored_count。"""
        zip_path = self.tmp_path / "v.zip"
        write_zip(zip_path, {"ok.md": "# OK\n\n正常内容"})
        settings = VaultSettings(data_dir=self.tmp_path / "data", max_file_size_mb=1)
        VaultImporter(settings).import_zip(zip_path)

        # 手动添加一个超大文件到 files/
        big_file = settings.files_dir / "big.md"
        big_file.write_text("# Big\n\n" + "x" * (2 * 1024 * 1024), encoding="utf-8")

        manifest = VaultImporter(settings).rebuild_from_files()
        self.assertEqual(manifest.file_count, 1)
        self.assertEqual(manifest.ignored_count, 1)

    def test_rebuild_ignores_disallowed_extensions(self):
        """rebuild_from_files 应跳过不允许的扩展名并统计 ignored_count。"""
        zip_path = self.tmp_path / "v.zip"
        write_zip(zip_path, {"ok.md": "# OK\n\n正常内容"})
        settings = VaultSettings(data_dir=self.tmp_path / "data")
        VaultImporter(settings).import_zip(zip_path)

        # 手动添加一个不允许的扩展名
        bad_file = settings.files_dir / "bad.xyz"
        bad_file.write_text("not markdown", encoding="utf-8")

        manifest = VaultImporter(settings).rebuild_from_files()
        self.assertEqual(manifest.file_count, 1)
        self.assertEqual(manifest.ignored_count, 1)

    def test_select_section_empty_heading_treated_as_none(self):
        """空字符串 heading 应与 None 行为一致:返回第一个标题。"""
        from core.reader import select_section
        headings = [
            {"level": 1, "title": "标题A", "line_start": 1, "line_end": 3},
            {"level": 2, "title": "标题B", "line_start": 4, "line_end": 5},
        ]
        body = "# 标题A\n\n内容A\n\n## 标题B\n内容B"

        result_none = select_section(body, headings, None)
        result_empty = select_section(body, headings, "")
        result_space = select_section(body, headings, "  ")

        self.assertEqual(result_none["heading"]["title"], "标题A")
        self.assertEqual(result_empty["heading"]["title"], "标题A")
        self.assertEqual(result_space["heading"]["title"], "标题A")

    def test_extract_callouts_stops_at_non_blockquote(self):
        """callout 捕获在遇到非 > 开头行时结束,不误捕获后续引用块。"""
        from core.reader import extract_callouts
        body = (
            "> [!summary] 这是摘要\n"
            "> 摘要内容\n"
            "\n"
            "普通段落\n"
            "\n"
            "> 这是普通引用,不是 callout\n"
            "> 不应被收集"
        )
        result = extract_callouts(body)
        self.assertIn("这是摘要", result)
        self.assertIn("摘要内容", result)
        self.assertNotIn("普通引用", result)

    def test_extract_callouts_multiple_callouts(self):
        """多个 callout 块应分别捕获。"""
        from core.reader import extract_callouts
        body = (
            "> [!summary] 摘要\n"
            "> 内容\n"
            "\n"
            "> [!warning] 警告\n"
            "> 警告内容"
        )
        result = extract_callouts(body)
        self.assertIn("摘要", result)
        self.assertIn("警告", result)


if __name__ == "__main__":
    unittest.main()
