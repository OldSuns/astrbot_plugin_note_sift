import shutil
import sys
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import VaultSettings
from core.importer import VaultImporter
from core.search import VaultSearch


def write_zip(path: Path, files: dict[str, str | bytes]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)


class RebuildTest(unittest.TestCase):
    def setUp(self):
        self.tmp_path = Path(__file__).parent / ".tmp_rebuild"
        if self.tmp_path.exists():
            shutil.rmtree(self.tmp_path)
        self.tmp_path.mkdir(parents=True)

    def tearDown(self):
        if self.tmp_path.exists():
            shutil.rmtree(self.tmp_path)

    def test_rebuild_from_files_recreates_index_without_zip(self):
        """RED: rebuild_from_files() should rebuild index from existing files/ directory."""
        data_dir = self.tmp_path / "data"
        settings = VaultSettings(data_dir=data_dir, vault_id="test_vault")
        importer = VaultImporter(settings)

        # Import initial zip
        zip_path = self.tmp_path / "vault.zip"
        write_zip(zip_path, {
            "note1.md": "# Note 1\n\nContent about async programming",
            "note2.md": "# Note 2\n\n#python #tutorial\n\nPython basics",
        })
        manifest = importer.import_zip(zip_path)
        self.assertEqual(manifest.file_count, 2)

        # Verify zip deleted
        self.assertFalse(zip_path.exists())

        # Verify files exist
        files_dir = settings.files_dir
        self.assertTrue((files_dir / "note1.md").exists())
        self.assertTrue((files_dir / "note2.md").exists())

        # Delete index to simulate corruption
        index_path = settings.index_path
        self.assertTrue(index_path.exists())
        index_path.unlink()
        self.assertFalse(index_path.exists())

        # Rebuild from files (zip is gone)
        new_manifest = importer.rebuild_from_files()

        # Verify index rebuilt
        self.assertTrue(index_path.exists())
        self.assertEqual(new_manifest.file_count, 2)
        self.assertEqual(new_manifest.vault_id, "test_vault")

        # Verify search works
        searcher = VaultSearch(settings)
        results = searcher.discover("async", limit=10)
        self.assertEqual(len(results), 1)
        self.assertIn("note1", results[0]["path"])


if __name__ == "__main__":
    unittest.main()
