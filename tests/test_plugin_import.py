import importlib
import sys
import types
import unittest
from pathlib import Path


class PluginImportTest(unittest.TestCase):
    def test_main_imports_core_when_loaded_as_package(self):
        plugin_root = Path(__file__).resolve().parents[1]
        parent = str(plugin_root.parent)
        sys.path.insert(0, parent)
        # Try both old and new package names for backward compatibility
        pkg_name = plugin_root.name  # matches actual folder name
        sys.modules.pop(f"{pkg_name}.main", None)
        self._install_astrbot_stubs()
        try:
            module = importlib.import_module(f"{pkg_name}.main")
        finally:
            if parent in sys.path:
                sys.path.remove(parent)
        self.assertTrue(hasattr(module, "NoteSiftPlugin"))

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

        class DummyContext:
            pass

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
        api.logger = types.SimpleNamespace(warning=lambda *_args, **_kwargs: None)
        event.AstrMessageEvent = DummyEvent
        event.filter = DummyFilter()
        star.Context = DummyContext
        star.Star = DummyStar
        star.register = register
        path_mod.get_astrbot_data_path = lambda: str(Path(__file__).parent / ".data")

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
