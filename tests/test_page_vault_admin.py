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

    def _make_plugin(self):
        context = types.SimpleNamespace(register_web_api=lambda *_args, **_kwargs: None)
        plugin = self.module.NoteSiftPlugin(context, {})
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
