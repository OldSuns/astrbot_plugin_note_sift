import importlib
import shutil
import sys
import types
import unittest
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


if __name__ == "__main__":
    unittest.main()
