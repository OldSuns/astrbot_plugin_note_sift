from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class VaultSettings:
    data_dir: Path
    vault_id: str = "default"
    allowed_extensions: set[str] = field(
        default_factory=lambda: {".md", ".markdown", ".txt"}
    )
    max_file_size_mb: int = 5
    max_read_chars: int = 8000
    max_discover_snippet_chars: int = 300
    full_over_limit_strategy: str = "strict"
    compressed_section_preview_chars: int = 200

    @property
    def root_dir(self) -> Path:
        return self.data_dir / "vaults" / self.vault_id

    @property
    def vault_dir(self) -> Path:
        return self.root_dir

    @property
    def files_dir(self) -> Path:
        return self.root_dir / "files"

    @property
    def index_path(self) -> Path:
        return self.root_dir / "index.sqlite3"

    @property
    def manifest_path(self) -> Path:
        return self.root_dir / "import_manifest.json"
