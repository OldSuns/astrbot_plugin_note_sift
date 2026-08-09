import shutil
import sys
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import VaultSettings
from core.importer import VaultImporter
from core.links import find_related


def write_zip(path: Path, files: dict) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)


class LinksTest(unittest.TestCase):
    def setUp(self):
        self.tmp_path = Path(__file__).parent / ".tmp_links"
        if self.tmp_path.exists():
            shutil.rmtree(self.tmp_path)
        self.tmp_path.mkdir(parents=True)

    def tearDown(self):
        if self.tmp_path.exists():
            shutil.rmtree(self.tmp_path)

    def _import(self, files):
        zip_path = self.tmp_path / "v.zip"
        write_zip(zip_path, files)
        settings = VaultSettings(data_dir=self.tmp_path / "data", vault_id="v")
        VaultImporter(settings).import_zip(zip_path)
        return settings

    def test_outlinks_and_backlinks_resolve_by_basename(self):
        settings = self._import(
            {
                "a.md": "# A\n\n参见 [[B]] 与 [[缺失笔记]]",
                "b.md": "---\naliases:\n  - 别名B\n---\n\n# B\n\n回看 [[A]]",
            }
        )
        from core.index import stable_note_id

        a_id = stable_note_id("v", "a.md")
        related = find_related(settings, a_id)

        out_targets = {o.get("note_id") for o in related["outlinks"] if o.get("note_id")}
        self.assertIn(stable_note_id("v", "b.md"), out_targets)
        self.assertTrue(any(o.get("resolved") is False for o in related["outlinks"]))

        back_ids = {b["note_id"] for b in related["backlinks"]}
        self.assertIn(stable_note_id("v", "b.md"), back_ids)

    def test_backlink_resolves_via_alias(self):
        settings = self._import(
            {
                "a.md": "---\naliases:\n  - 别名B\n---\n\n# A",
                "c.md": "# C\n\n通过别名 [[别名B]] 链接",
            }
        )
        from core.index import stable_note_id

        related = find_related(settings, stable_note_id("v", "a.md"))
        back_ids = {b["note_id"] for b in related["backlinks"]}
        self.assertIn(stable_note_id("v", "c.md"), back_ids)


if __name__ == "__main__":
    unittest.main()
