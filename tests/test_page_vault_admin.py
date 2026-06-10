import importlib
import json
import shutil
import sqlite3
import sys
import types
import unittest
import zipfile
from pathlib import Path


class PageVaultAdminTest(unittest.TestCase):
    def setUp(self):
        self.tmp_path = Path(__file__).parent / ".tmp_page_vault_admin"
        if self.tmp_path.exists():
            shutil.rmtree(self.tmp_path)
        self.tmp_path.mkdir(parents=True)

        self.plugin_root = Path(__file__).resolve().parents[1]
        self.parent = str(self.plugin_root.parent)
        sys.path.insert(0, self.parent)
        self._install_astrbot_stubs()
        sys.modules.pop(f"{self.plugin_root.name}.main", None)
        self.module = importlib.import_module(f"{self.plugin_root.name}.main")

    def tearDown(self):
        if self.parent in sys.path:
            sys.path.remove(self.parent)
        if self.tmp_path.exists():
            shutil.rmtree(self.tmp_path)

    def test_upload_vault_id_falls_back_to_zip_filename(self):
        plugin = self._make_plugin()

        vault_id = plugin._resolve_upload_vault_id("", Path("Medical Notes.zip"))

        self.assertEqual(vault_id, "Medical_Notes")

    def test_delete_vault_rejects_path_traversal(self):
        plugin = self._make_plugin()

        with self.assertRaises(ValueError):
            plugin._delete_vault_data("../default")

    def test_delete_vault_removes_only_target_directory(self):
        plugin = self._make_plugin()
        vaults_dir = plugin.data_dir / "vaults"
        target = vaults_dir / "target"
        other = vaults_dir / "other"
        (target / "files").mkdir(parents=True)
        (other / "files").mkdir(parents=True)
        (target / "files" / "note.md").write_text("# Target", encoding="utf-8")
        (other / "files" / "note.md").write_text("# Other", encoding="utf-8")

        plugin._delete_vault_data("target")

        self.assertFalse(target.exists())
        self.assertTrue(other.exists())
        self.assertTrue((other / "files" / "note.md").exists())

    def test_imported_at_can_be_derived_from_legacy_import_id(self):
        imported_at = self.module.imported_at_from_import_id("1700000000000")

        self.assertEqual(imported_at, "2023-11-14T22:13:20+00:00")

    def test_get_available_vaults_ignores_empty_ghost_vault(self):
        plugin = self._make_plugin()
        ghost = plugin.data_dir / "vaults" / "default"
        ghost.mkdir(parents=True)
        db = sqlite3.connect(ghost / "index.sqlite3")
        try:
            db.execute("create table notes(note_id text)")
            db.commit()
        finally:
            db.close()

        real = plugin.data_dir / "vaults" / "medical"
        real.mkdir(parents=True)
        (real / "import_manifest.json").write_text(
            json.dumps({"file_count": 1}),
            encoding="utf-8",
        )

        vaults = plugin._get_available_vaults()

        self.assertEqual([vault["vault_id"] for vault in vaults], ["medical"])

    def test_kb_read_without_vault_id_resolves_across_vaults(self):
        plugin = self._make_plugin()
        zip_path = self.tmp_path / "medical.zip"
        self._write_zip(zip_path, {"口腔医学/0.期末考试范围.md": "# 期末考试范围\n\n牙体牙髓重点"})
        settings = self.module.VaultSettings(data_dir=plugin.data_dir, vault_id="临床医学")
        self.module.VaultImporter(settings).import_zip(zip_path)
        event = types.SimpleNamespace(unified_msg_origin="umo")

        result = self._run_async(
            plugin.kb_read(
                event,
                note_ref="口腔医学/0.期末考试范围.md",
                mode="outline",
            )
        )

        payload = json.loads(result)
        self.assertTrue(payload["found"])
        self.assertEqual(payload["vault_id"], "临床医学")
        self.assertEqual(payload["title"], "期末考试范围")
        self.assertFalse((plugin.data_dir / "vaults" / "default").exists())

    def test_kb_discover_returns_compact_results_by_default(self):
        plugin = self._make_plugin()
        zip_path = self.tmp_path / "medical.zip"
        self._write_zip(
            zip_path,
            {"口腔医学/0.期末考试范围.md": "# 口腔医学期末考试复习范围\n\n牙体牙髓重点"},
        )
        settings = self.module.VaultSettings(data_dir=plugin.data_dir, vault_id="临床医学")
        self.module.VaultImporter(settings).import_zip(zip_path)
        event = types.SimpleNamespace(unified_msg_origin="umo")

        result = self._run_async(plugin.kb_discover(event, query="口腔", limit=5))

        item = json.loads(result)["results"][0]
        self.assertEqual(item["rank"], 1)
        self.assertEqual(item["ref"], f"临床医学:{item['note_id']}")
        self.assertEqual(item["vault_id"], "临床医学")
        self.assertEqual(item["path"], "口腔医学/0.期末考试范围.md")
        self.assertEqual(item["title"], "口腔医学期末考试复习范围")
        self.assertIn("title", item["matched"])
        self.assertNotIn("matched_fields", item)
        self.assertNotIn("score", item)
        self.assertNotIn("tags", item)
        self.assertNotIn("aliases", item)
        self.assertNotIn("source_ref", item)
        self.assertNotIn("snippets", item)

    def test_kb_discover_verbose_keeps_debug_fields(self):
        plugin = self._make_plugin()
        zip_path = self.tmp_path / "medical.zip"
        self._write_zip(
            zip_path,
            {"口腔医学/0.期末考试范围.md": "---\ntags:\n  - 口腔医学\naliases:\n  - 口腔复习\n---\n\n# 期末考试范围\n\n牙体牙髓重点"},
        )
        settings = self.module.VaultSettings(data_dir=plugin.data_dir, vault_id="临床医学")
        self.module.VaultImporter(settings).import_zip(zip_path)
        event = types.SimpleNamespace(unified_msg_origin="umo")

        result = self._run_async(plugin.kb_discover(event, query="牙髓", limit=5, verbose=True))

        item = json.loads(result)["results"][0]
        self.assertIn("score", item)
        self.assertEqual(item["tags"], ["口腔医学"])
        self.assertEqual(item["aliases"], ["口腔复习"])
        self.assertIn("snippets", item)
        self.assertNotIn("matched_fields", item)
        self.assertNotIn("source_ref", item)

    def test_kb_read_returns_compact_outline_by_default(self):
        plugin = self._make_plugin()
        zip_path = self.tmp_path / "medical.zip"
        self._write_zip(
            zip_path,
            {"口腔医学/0.期末考试范围.md": "---\ntags:\n  - 口腔医学\naliases:\n  - 口腔复习\n---\n\n# 期末考试范围\n\n## 重点章节\n牙体牙髓重点"},
        )
        settings = self.module.VaultSettings(data_dir=plugin.data_dir, vault_id="临床医学")
        self.module.VaultImporter(settings).import_zip(zip_path)
        event = types.SimpleNamespace(unified_msg_origin="umo")

        result = self._run_async(
            plugin.kb_read(event, note_ref="口腔医学/0.期末考试范围.md", mode="outline")
        )

        payload = json.loads(result)
        self.assertTrue(payload["found"])
        self.assertEqual(payload["ref"], f"临床医学:{payload['note_id']}")
        self.assertEqual(payload["vault_id"], "临床医学")
        self.assertEqual(payload["mode"], "outline")
        self.assertIn("headings", payload)
        self.assertNotIn("tags", payload)
        self.assertNotIn("aliases", payload)
        self.assertNotIn("source_ref", payload)
        self.assertNotIn("content", payload)
        self.assertNotIn("truncated", payload)
        self.assertNotIn("next_action_hint", payload)

    def test_kb_read_verbose_keeps_metadata(self):
        plugin = self._make_plugin()
        zip_path = self.tmp_path / "medical.zip"
        self._write_zip(
            zip_path,
            {"口腔医学/0.期末考试范围.md": "---\ntags:\n  - 口腔医学\naliases:\n  - 口腔复习\n---\n\n# 期末考试范围\n\n正文"},
        )
        settings = self.module.VaultSettings(data_dir=plugin.data_dir, vault_id="临床医学")
        self.module.VaultImporter(settings).import_zip(zip_path)
        event = types.SimpleNamespace(unified_msg_origin="umo")

        result = self._run_async(
            plugin.kb_read(event, note_ref="口腔医学/0.期末考试范围.md", mode="outline", verbose=True)
        )

        payload = json.loads(result)
        self.assertEqual(payload["tags"], ["口腔医学"])
        self.assertEqual(payload["aliases"], ["口腔复习"])
        self.assertNotIn("source_ref", payload)

    def test_kb_read_section_reports_heading_match(self):
        plugin = self._make_plugin()
        zip_path = self.tmp_path / "medical.zip"
        self._write_zip(
            zip_path,
            {"口腔医学/0.期末考试范围.md": "# 期末考试范围\n\n## 重点章节\n牙体牙髓重点\n\n## 其他\n内容"},
        )
        settings = self.module.VaultSettings(data_dir=plugin.data_dir, vault_id="临床医学")
        self.module.VaultImporter(settings).import_zip(zip_path)
        event = types.SimpleNamespace(unified_msg_origin="umo")

        result = self._run_async(
            plugin.kb_read(event, note_ref="口腔医学/0.期末考试范围.md", mode="section", heading="重点")
        )

        payload = json.loads(result)
        self.assertTrue(payload["heading_matched"])
        self.assertEqual(payload["heading"]["title"], "重点章节")
        self.assertIn("牙体牙髓重点", payload["content"])
        self.assertNotIn("headings", payload)

    def test_kb_read_section_reports_heading_not_found(self):
        plugin = self._make_plugin()
        zip_path = self.tmp_path / "medical.zip"
        self._write_zip(
            zip_path,
            {"口腔医学/0.期末考试范围.md": "# 期末考试范围\n\n## 重点章节\n牙体牙髓重点\n\n#### 细节\n内容"},
        )
        settings = self.module.VaultSettings(data_dir=plugin.data_dir, vault_id="临床医学")
        self.module.VaultImporter(settings).import_zip(zip_path)
        event = types.SimpleNamespace(unified_msg_origin="umo")

        result = self._run_async(
            plugin.kb_read(event, note_ref="口腔医学/0.期末考试范围.md", mode="section", heading="不存在")
        )

        payload = json.loads(result)
        self.assertFalse(payload["found"])
        self.assertEqual(payload["error"], "heading not found")
        self.assertEqual(payload["ref"], f"临床医学:{payload['note_id']}")
        self.assertEqual(payload["vault_id"], "临床医学")
        self.assertEqual(payload["mode"], "section")
        self.assertEqual(payload["requested_heading"], "不存在")
        self.assertEqual(
            [heading["title"] for heading in payload["available_headings"]],
            ["期末考试范围", "重点章节"],
        )
        self.assertNotIn("content", payload)

    def test_kb_read_full_over_limit_returns_headings_up_to_level_three(self):
        plugin = self._make_plugin(config={"max_read_chars": 40})
        zip_path = self.tmp_path / "medical.zip"
        self._write_zip(
            zip_path,
            {
                "口腔医学/0.期末考试范围.md": "# 期末考试范围\n\n## 二级\n" + "x" * 80 + "\n\n### 三级\n内容\n\n#### 四级\n细节",
            },
        )
        settings = self.module.VaultSettings(data_dir=plugin.data_dir, vault_id="临床医学")
        self.module.VaultImporter(settings).import_zip(zip_path)
        event = types.SimpleNamespace(unified_msg_origin="umo")

        result = self._run_async(
            plugin.kb_read(event, note_ref="口腔医学/0.期末考试范围.md", mode="full", vault_id="临床医学")
        )

        payload = json.loads(result)
        self.assertTrue(payload["truncated"])
        self.assertEqual([heading["level"] for heading in payload["headings"]], [1, 2, 3])
        self.assertEqual([heading["title"] for heading in payload["headings"]], ["期末考试范围", "二级", "三级"])

    def _make_plugin(self, config=None):
        context = types.SimpleNamespace(register_web_api=lambda *_args, **_kwargs: None)
        plugin = self.module.NoteSiftPlugin(context, config or {})
        plugin.data_dir = self.tmp_path / "data"
        return plugin

    def _install_astrbot_stubs(self):
        astrbot = types.ModuleType("astrbot")
        api = types.ModuleType("astrbot.api")
        event = types.ModuleType("astrbot.api.event")
        star = types.ModuleType("astrbot.api.star")
        core = types.ModuleType("astrbot.core")
        utils = types.ModuleType("astrbot.core.utils")
        path_mod = types.ModuleType("astrbot.core.utils.astrbot_path")

        class DummyConfig(dict):
            pass

        class DummyEvent:
            pass

        class DummyStar:
            def __init__(self, context):
                self.context = context

        class DummyFilter:
            class PermissionType:
                ADMIN = "admin"

            def command_group(self, *_args, **_kwargs):
                def decorator(func):
                    func.command = self.command
                    return func
                return decorator

            def command(self, *_args, **_kwargs):
                def decorator(func):
                    return func
                return decorator

            def permission_type(self, *_args, **_kwargs):
                return self.command()

            def llm_tool(self, *_args, **_kwargs):
                return self.command()

        def register(*_args, **_kwargs):
            def decorator(cls):
                return cls
            return decorator

        api.AstrBotConfig = DummyConfig
        api.logger = types.SimpleNamespace(
            warning=lambda *_args, **_kwargs: None,
            error=lambda *_args, **_kwargs: None,
            info=lambda *_args, **_kwargs: None,
        )
        event.AstrMessageEvent = DummyEvent
        event.filter = DummyFilter()
        star.Context = object
        star.Star = DummyStar
        star.register = register
        path_mod.get_astrbot_data_path = lambda: str(self.tmp_path / "astrbot_data")

        sys.modules.update(
            {
                "astrbot": astrbot,
                "astrbot.api": api,
                "astrbot.api.event": event,
                "astrbot.api.star": star,
                "astrbot.core": core,
                "astrbot.core.utils": utils,
                "astrbot.core.utils.astrbot_path": path_mod,
            }
        )

    def _write_zip(self, path: Path, files: dict[str, str | bytes]) -> None:
        with zipfile.ZipFile(path, "w") as archive:
            for name, content in files.items():
                archive.writestr(name, content)

    def _run_async(self, coro):
        import asyncio

        return asyncio.run(coro)


if __name__ == "__main__":
    unittest.main()
