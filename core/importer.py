import hashlib
import json
import re
import shutil
import time
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

from .config import VaultSettings
from .index import VaultIndex
from .markdown import parse_markdown


class ImportErrorInfo(Exception):
    pass


@dataclass
class ImportManifest:
    import_id: str
    vault_id: str
    zip_hash: str
    file_count: int
    ignored_count: int
    fts_available: bool
    vault_root: str = ""


class VaultImporter:
    def __init__(self, settings: VaultSettings):
        self.settings = settings

    def rebuild_from_files(self) -> ImportManifest:
        """Rebuild index from existing files/ directory without needing the original zip."""
        files_dir = self.settings.files_dir
        if not files_dir.exists():
            raise ImportErrorInfo(f"files directory not found: {files_dir}")

        import_id = str(int(time.time() * 1000))
        tmp_dir = self.settings.data_dir / "tmp_rebuild" / import_id
        staging_index = tmp_dir / "index.sqlite3"
        final_index = self.settings.index_path

        try:
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir)
            tmp_dir.mkdir(parents=True, exist_ok=True)

            # Scan existing files
            notes = []
            file_count = 0
            for file_path in sorted(files_dir.rglob("*")):
                if not file_path.is_file():
                    continue
                suffix = file_path.suffix.lower()
                if suffix not in self.settings.allowed_extensions:
                    continue
                relative_path = file_path.relative_to(files_dir).as_posix()
                text = file_path.read_text(encoding="utf-8", errors="replace")
                parsed = parse_markdown(text, Path(relative_path).stem)
                notes.append((relative_path, file_path, parsed))
                file_count += 1

            # Rebuild index
            index = VaultIndex(staging_index, self.settings.vault_id)
            index.rebuild_notes(files_dir, notes)

            # Replace old index with new one
            final_index.parent.mkdir(parents=True, exist_ok=True)
            if final_index.exists():
                final_index.unlink()
            shutil.move(str(staging_index), str(final_index))

            manifest = ImportManifest(
                import_id=import_id,
                vault_id=self.settings.vault_id,
                zip_hash="",  # No zip for rebuild
                file_count=file_count,
                ignored_count=0,  # Not applicable for rebuild
                fts_available=VaultIndex(final_index, self.settings.vault_id).fts_available(),
                vault_root="",
            )
            self.settings.manifest_path.write_text(
                json.dumps(asdict(manifest), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return manifest
        except Exception as error:
            if isinstance(error, ImportErrorInfo):
                raise
            raise ImportErrorInfo(str(error)) from error
        finally:
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir, ignore_errors=True)

    def import_zip(self, zip_path: Path) -> ImportManifest:
        zip_path = Path(zip_path)
        if not zip_path.exists():
            raise ImportErrorInfo(f"zip file not found: {zip_path}")
        zip_hash = sha1_file(zip_path)
        import_id = str(int(time.time() * 1000))
        tmp_dir = self.settings.data_dir / "tmp_import" / import_id
        staging_files = tmp_dir / "files"
        staging_index = tmp_dir / "index.sqlite3"
        final_dir = self.settings.files_dir
        final_index = self.settings.index_path
        try:
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir)
            staging_files.mkdir(parents=True, exist_ok=True)

            # Detect Obsidian vault root
            vault_root = detect_obsidian_vault_root(zip_path)

            file_count, ignored_count = self._extract_zip(zip_path, staging_files, vault_root)
            notes = []
            for file_path in sorted(staging_files.rglob("*")):
                if not file_path.is_file():
                    continue
                relative_path = file_path.relative_to(staging_files).as_posix()
                text = file_path.read_text(encoding="utf-8", errors="replace")
                parsed = parse_markdown(text, Path(relative_path).stem)
                notes.append((relative_path, file_path, parsed))
            index = VaultIndex(staging_index, self.settings.vault_id)
            index.rebuild_notes(staging_files, notes)
            if final_dir.exists():
                shutil.rmtree(final_dir)
            final_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(staging_files), str(final_dir))
            final_index.parent.mkdir(parents=True, exist_ok=True)
            if final_index.exists():
                final_index.unlink()
            shutil.move(str(staging_index), str(final_index))
            manifest = ImportManifest(
                import_id=import_id,
                vault_id=self.settings.vault_id,
                zip_hash=zip_hash,
                file_count=file_count,
                ignored_count=ignored_count,
                fts_available=VaultIndex(final_index, self.settings.vault_id).fts_available(),
                vault_root=vault_root,
            )
            self.settings.manifest_path.write_text(
                json.dumps(asdict(manifest), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            zip_path.unlink(missing_ok=True)
            return manifest
        except Exception as error:
            if isinstance(error, ImportErrorInfo):
                raise
            raise ImportErrorInfo(str(error)) from error
        finally:
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir, ignore_errors=True)

    def _extract_zip(self, zip_path: Path, destination: Path, vault_root: str = "") -> tuple[int, int]:
        file_count = 0
        ignored_count = 0
        with zipfile.ZipFile(zip_path) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                relative = safe_zip_path(info.filename)

                # If vault_root detected, only extract files under that directory
                if vault_root:
                    if not relative.as_posix().startswith(vault_root + "/"):
                        ignored_count += 1
                        continue
                    # Strip vault_root prefix from path
                    relative = PurePosixPath(*relative.parts[len(PurePosixPath(vault_root).parts):])

                suffix = Path(relative.name).suffix.lower()
                if suffix not in self.settings.allowed_extensions:
                    ignored_count += 1
                    continue
                if info.file_size > self.settings.max_file_size_mb * 1024 * 1024:
                    ignored_count += 1
                    continue
                target = destination / relative.as_posix()
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
                file_count += 1
        return file_count, ignored_count


def safe_zip_path(name: str) -> PurePosixPath:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or not path.parts:
        raise ImportErrorInfo(f"unsafe path: {name}")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ImportErrorInfo(f"unsafe path: {name}")
    if any(len(part) > 180 for part in path.parts) or len(path.as_posix()) > 500:
        raise ImportErrorInfo(f"unsafe path: {name}")
    return path


def sha1_file(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_vault_id_from_path(path: Path) -> str:
    """Extract vault_id from zip filename, sanitizing special characters."""
    stem = path.stem  # Remove .zip extension
    # Replace special characters with underscores
    sanitized = re.sub(r'[^\w一-鿿]+', '_', stem)
    # Remove leading/trailing underscores
    sanitized = sanitized.strip('_')
    return sanitized if sanitized else "default"


def detect_obsidian_vault_root(zip_path: Path) -> str:
    """Detect Obsidian vault root by finding .obsidian directory.

    Returns:
        Empty string if no .obsidian found, otherwise the parent directory path.
    """
    with zipfile.ZipFile(zip_path) as archive:
        for name in archive.namelist():
            # Look for .obsidian directory
            if "/.obsidian/" in name or name.endswith("/.obsidian"):
                parts = name.replace("\\", "/").split("/")
                # Find the parent of .obsidian
                try:
                    obsidian_index = parts.index(".obsidian")
                    if obsidian_index > 0:
                        return "/".join(parts[:obsidian_index])
                except ValueError:
                    continue
    return ""
