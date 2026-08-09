from pathlib import Path
from typing import Any
import re
import shutil

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

try:
    from .core.config import VaultSettings
    from .core.importer import ImportErrorInfo, VaultImporter, extract_vault_id_from_path
    from .core.links import find_related
    from .core.reader import VaultReader
    from .core.search import VaultSearch, grep_across_vaults, search_across_vaults
except ImportError:
    from core.config import VaultSettings
    from core.importer import ImportErrorInfo, VaultImporter, extract_vault_id_from_path
    from core.links import find_related
    from core.reader import VaultReader
    from core.search import VaultSearch, grep_across_vaults, search_across_vaults

try:
    from astrbot.core.utils.astrbot_path import get_astrbot_data_path
except Exception:
    get_astrbot_data_path = None


PLUGIN_NAME = "astrbot_plugin_note_sift"

READ_MODES = ("outline", "summary", "section", "snippets", "full")
OVER_LIMIT_STRATEGIES = ("strict", "paged", "compressed")


@register(PLUGIN_NAME, "OldSun", "NoteSift - Grep-first Markdown/Obsidian knowledge base for AstrBot", "0.2.0")
class NoteSiftPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.data_dir = self._determine_data_dir()
        self._last_search_by_session: dict[str, list[dict[str, Any]]] = {}
        self._register_web_apis(context)

    async def initialize(self):
        await self._import_all_configured_vaults()

    def _register_web_apis(self, context: Context):
        """Register web APIs for plugin pages."""
        try:
            context.register_web_api(
                f"/{PLUGIN_NAME}/vaults",
                self.page_get_vaults,
                ["GET"],
                "Get all vaults status"
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/config",
                self.page_config,
                ["GET", "POST"],
                "Get or update plugin config"
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/vault/import",
                self.page_import_vault,
                ["POST"],
                "Upload and import a vault zip"
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/vault/rebuild",
                self.page_rebuild_vault,
                ["POST"],
                "Rebuild a vault index"
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/vault/<vault_id>",
                self.page_delete_vault,
                ["DELETE"],
                "Delete a vault"
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/vault/delete",
                self.page_delete_vault_post,
                ["POST"],
                "Delete a vault"
            )
        except Exception as e:
            logger.warning(f"Failed to register web APIs: {e}")

    @filter.command_group("kb")
    def kb(self):
        """知识库搜索/读取/管理命令组。支持多库隔离与全文检索。"""

    @kb.command("search")
    async def kb_search(self, event: AstrMessageEvent, query: str):
        """搜索知识库候选笔记。支持 vault_id:query 前缀指定库，如 medical:川崎病。"""
        if not self._is_allowed(event):
            yield event.plain_result("当前会话未授权访问知识库。")
            return
        vault_id, search_query = self._parse_vault_query(query)
        results = search_across_vaults(self.data_dir, search_query, limit=8, vault_id=vault_id, max_discover_snippet_chars=int(self.config.get("max_discover_snippet_chars", 300)))
        self._last_search_by_session[event.unified_msg_origin] = results
        yield event.plain_result(render_search_results(results))

    @kb.command("read")
    async def kb_read_command(self, event: AstrMessageEvent, note_ref: str, mode: str = "", page: str = "1"):
        """读取指定笔记。note_ref 可用搜索结果编号、vault_id:note_id 或 vault_id:path。page 用于 paged 模式分页。"""
        if not self._is_allowed(event):
            yield event.plain_result("当前会话未授权访问知识库。")
            return
        vault_id, resolved_ref = self._resolve_note_ref(event.unified_msg_origin, note_ref)
        read_mode = mode or self.config.get("default_read_mode", "outline")

        # Validate page parameter
        page_num = validate_int_param(page, default=1, min_val=1)

        settings = self._build_settings(vault_id)
        reader = VaultReader(settings)
        result = reader.read_note(resolved_ref, mode=read_mode, page=page_num)
        yield event.plain_result(render_read_result(result))

    @kb.command("grep")
    async def kb_grep(self, event: AstrMessageEvent, query: str):
        """按正文 grep 返回命中片段。支持 vault_id:query 前缀。"""
        if not self._is_allowed(event):
            yield event.plain_result("当前会话未授权访问知识库。")
            return
        vault_id, search_query = self._parse_vault_query(query)

        results = grep_across_vaults(self.data_dir, search_query, limit=8, vault_id=vault_id)
        yield event.plain_result(render_grep_results(results))

    @kb.command("status")
    async def kb_status(self, event: AstrMessageEvent):
        """查看所有知识库导入和索引状态。"""
        if not self._is_allowed(event):
            yield event.plain_result("当前会话未授权访问知识库。")
            return
        yield event.plain_result(self._status_text())

    @filter.permission_type(filter.PermissionType.ADMIN)
    @kb.command("rebuild")
    async def kb_rebuild(self, event: AstrMessageEvent, vault_id: str = ""):
        """管理员命令：从已导入的 files 目录重建指定知识库索引。不指定则重建所有库。"""
        try:
            manifests = await self._rebuild_all_vaults(specific_vault=vault_id or None)
        except ImportErrorInfo as error:
            yield event.plain_result(f"重建失败：{error}")
            return
        if manifests:
            summary = []
            for m in manifests:
                summary.append(f"{m.vault_id}: {m.file_count} 个文件")
            yield event.plain_result("重建完成：\n" + "\n".join(summary))
        else:
            yield event.plain_result("未找到已导入的知识库，无法重建。")

    @filter.llm_tool(name="kb_list_vaults")
    async def kb_list_vaults(self, event: AstrMessageEvent) -> str:
        """列出所有可用的知识库。使用此工具获取可以在其他 kb_ 工具中使用的 vault_id。

        Returns: 返回可用知识库的 ID 列表和基本信息
        """
        if not self._is_allowed(event):
            return "Knowledge vault access denied for this session."

        vaults_info = self._get_available_vaults()
        return format_tool_payload({"vaults": vaults_info})

    @filter.llm_tool(name="kb_discover")
    async def kb_discover(self, event: AstrMessageEvent, query: str, limit: int = 5, regex: bool = False, vault_id: str = "", verbose: bool = False) -> str:
        """发现知识库候选笔记，默认返回精简字段；verbose=true 时返回调试字段。

        Args:
            query(string): 搜索关键词或正则表达式
            limit(number): 返回候选数量，默认 5
            regex(boolean): 是否按正则表达式搜索，默认 false
            vault_id(string): 指定知识库 ID，留空则跨库搜索。
                             提示：先使用 kb_list_vaults 工具获取可用的知识库 ID
            verbose(boolean): 是否返回 score、tags、aliases 等调试字段，默认 false
        """
        if not self._is_allowed(event):
            return "Knowledge vault access denied for this session."

        # Validate limit parameter
        validated_limit = validate_int_param(limit, default=5, min_val=1, max_val=10)

        results = search_across_vaults(
            self.data_dir,
            query,
            limit=validated_limit,
            regex=bool(regex),
            vault_id=vault_id or None,
            max_discover_snippet_chars=int(self.config.get("max_discover_snippet_chars", 300)),
        )
        return format_tool_payload({"results": format_discover_results(results, verbose=bool(verbose))})

    @filter.llm_tool(name="kb_read")
    async def kb_read(self, event: AstrMessageEvent, note_ref: str, mode: str = "outline", heading: str = "", query: str = "", page: int = 1, vault_id: str = "", verbose: bool = False) -> str:
        """读取知识库笔记。优先使用 outline 或 summary，再按 section 读取，full 可能因长度上限被拒绝或分页。

        Args:
            note_ref(string): note_id 或 path
            mode(string): 读取模式，可选 outline、summary、section、snippets、full
            heading(string): section 模式下的标题关键词
            query(string): snippets 模式下的检索词
            page(number): paged 模式下的页码，默认 1
            vault_id(string): 指定知识库 ID，留空则使用 note_ref 中的前缀或跨库解析。
                             提示：先使用 kb_list_vaults 工具获取可用的知识库 ID
            verbose(boolean): 是否返回 tags、aliases 等元数据，默认 false
        """
        if not self._is_allowed(event):
            return "Knowledge vault access denied for this session."

        # Validate page parameter
        validated_page = validate_int_param(page, default=1, min_val=1)

        target_vault, note_ref, candidates = self._resolve_read_target(note_ref, vault_id)
        if not target_vault:
            if candidates:
                return format_tool_payload(
                    {
                        "found": False,
                        "error": "ambiguous",
                        "candidates": candidates,
                        "next_action_hint": "该 note 在多个知识库存在，请用 vault_id 或 vault_id:note_ref 指定。",
                    }
                )
            return format_tool_payload({"found": False, "error": "note not found"})

        settings = self._build_settings(target_vault)
        reader = VaultReader(settings)

        read_mode = mode or "outline"
        result = reader.read_note(
            note_ref,
            mode=read_mode,
            heading=heading or None,
            query=query or None,
            page=validated_page
        )
        if result.get("found"):
            result["vault_id"] = target_vault
        return format_tool_payload(format_read_result(result, target_vault, read_mode, verbose=bool(verbose)))

    @filter.llm_tool(name="kb_related")
    async def kb_related(self, event: AstrMessageEvent, note_ref: str, vault_id: str = "") -> str:
        """查看某篇笔记的双链关系：返回它链出的笔记(outlinks)与链入它的笔记(backlinks)。

        Args:
            note_ref(string): note_id 或 path，可用 vault_id:note_ref 前缀
            vault_id(string): 指定知识库 ID，留空则按前缀或跨库解析
        """
        if not self._is_allowed(event):
            return "Knowledge vault access denied for this session."

        target_vault, note_ref, candidates = self._resolve_read_target(note_ref, vault_id)
        if not target_vault:
            if candidates:
                return format_tool_payload(
                    {"found": False, "error": "ambiguous", "candidates": candidates}
                )
            return format_tool_payload({"found": False, "error": "note not found"})

        settings = self._build_settings(target_vault)
        resolved = VaultReader(settings).read_note(note_ref, mode="outline")
        if not resolved.get("found"):
            return format_tool_payload({"found": False, "error": "note not found"})

        related = find_related(settings, resolved["note_id"])
        return format_tool_payload(related)

    def _build_settings(self, vault_id: str = "default") -> VaultSettings:
        return VaultSettings(
            data_dir=self.data_dir,
            vault_id=vault_id,
            max_read_chars=int(self.config.get("max_read_chars", 8000)),
            max_discover_snippet_chars=int(self.config.get("max_discover_snippet_chars", 300)),
            full_over_limit_strategy=str(self.config.get("full_over_limit_strategy", "strict")),
            compressed_section_preview_chars=int(self.config.get("compressed_section_preview_chars", 200)),
        )

    def _determine_data_dir(self) -> Path:
        # 使用 AstrBot 数据目录
        if get_astrbot_data_path:
            return Path(get_astrbot_data_path()) / "plugin_data" / PLUGIN_NAME
        else:
            # 降级到插件目录（如果 AstrBot API 不可用）
            return Path(__file__).parent / "data"

    async def _import_all_configured_vaults(self, force: bool = False, specific_vault: str | None = None):
        # 支持新旧配置格式
        vaults_config = self.config.get("vaults", [])
        vault_zip = self.config.get("vault_zip")

        # 如果使用旧的 vault_zip 配置
        if vault_zip and not vaults_config:
            # 转换为新格式
            if isinstance(vault_zip, str):
                vaults_config = [{"path": vault_zip}]
            elif isinstance(vault_zip, list):
                vaults_config = [{"path": p} if isinstance(p, str) else p for p in vault_zip]
            elif isinstance(vault_zip, dict):
                vaults_config = [vault_zip]

        if not vaults_config:
            return []

        manifests = []
        for vault_cfg in vaults_config:
            if not isinstance(vault_cfg, dict):
                continue

            vault_id = vault_cfg.get("id", "")
            zip_path_str = vault_cfg.get("path", "")

            if not zip_path_str:
                continue

            if specific_vault and vault_id != specific_vault:
                continue

            # Convert relative path to absolute (relative to data_dir)
            zip_path = Path(zip_path_str)
            if not zip_path.is_absolute():
                zip_path = self.data_dir / zip_path_str

            if not zip_path.exists():
                logger.warning(f"Vault zip not found: {zip_path}")
                continue

            # Auto-generate vault_id from filename if not provided
            if not vault_id:
                vault_id = extract_vault_id_from_path(zip_path)

            settings = self._build_settings(vault_id)
            try:
                manifest = VaultImporter(settings).import_zip(zip_path)
                manifests.append(manifest)
                logger.info(f"Imported vault '{vault_id}': {manifest.file_count} files")
            except ImportErrorInfo as error:
                logger.error(f"Failed to import vault '{vault_id}': {error}")

        return manifests

    async def _rebuild_all_vaults(self, specific_vault: str | None = None):
        """Rebuild index from existing files/ directories without needing zip files."""
        vaults_dir = self.data_dir / "vaults"
        if not vaults_dir.exists():
            return []

        vault_dirs = [d for d in vaults_dir.iterdir() if d.is_dir()]
        if not vault_dirs:
            return []

        manifests = []
        for vault_dir in vault_dirs:
            vault_id = vault_dir.name

            # Skip if specific vault requested and this isn't it
            if specific_vault and vault_id != specific_vault:
                continue

            settings = self._build_settings(vault_id)

            # Check if files/ directory exists
            if not settings.files_dir.exists():
                logger.warning(f"Vault '{vault_id}' has no files directory, skipping")
                continue

            try:
                manifest = VaultImporter(settings).rebuild_from_files()
                manifests.append(manifest)
                logger.info(f"Rebuilt vault '{vault_id}': {manifest.file_count} files")
            except ImportErrorInfo as error:
                logger.error(f"Failed to rebuild vault '{vault_id}': {error}")

        return manifests

    def _parse_vault_query(self, query: str) -> tuple[str | None, str]:
        """Parse 'vault_id:query' format. Returns (vault_id, query)."""
        if ":" in query:
            parts = query.split(":", 1)
            return parts[0], parts[1]
        return None, query

    def _is_allowed(self, event: AstrMessageEvent) -> bool:
        if not bool(self.config.get("enable_acl", False)):
            return True
        allowed = parse_allowed_sessions(self.config.get("allowed_sessions"))
        return event.unified_msg_origin in allowed

    def _resolve_note_ref(self, umo: str, note_ref: str) -> tuple[str, str]:
        """Resolve note reference. Returns (vault_id, note_ref)."""
        # Check for vault_id:ref format
        if ":" in note_ref:
            parts = note_ref.split(":", 1)
            return parts[0], parts[1]

        # Check if it's a search result number
        if note_ref.isdigit():
            index = int(note_ref) - 1
            results = self._last_search_by_session.get(umo, [])
            if 0 <= index < len(results):
                vault_id = results[index].get("vault_id", "default")
                return vault_id, results[index]["note_id"]

        # Default vault
        return "default", note_ref

    def _resolve_read_target(self, note_ref: str, vault_id: str = "") -> tuple[str | None, str, list[dict]]:
        """Returns (vault_id_or_None, note_ref, candidates).

        candidates 仅在跨库出现多个同名命中时非空。
        """
        if ":" in note_ref and not vault_id:
            parts = note_ref.split(":", 1)
            return parts[0], parts[1], []
        if vault_id:
            return vault_id, note_ref, []

        matches = self._find_note_across_vaults(note_ref)
        if len(matches) == 1:
            return matches[0]["vault_id"], note_ref, []
        if len(matches) > 1:
            return None, note_ref, matches
        return None, note_ref, []

    def _find_note_across_vaults(self, note_ref: str) -> list[dict]:
        vaults_dir = self.data_dir / "vaults"
        if not vaults_dir.exists():
            return []

        matches = []
        for vault_dir in sorted(d for d in vaults_dir.iterdir() if d.is_dir()):
            settings = self._build_settings(vault_dir.name)
            if not settings.index_path.exists():
                continue
            found = VaultReader(settings).read_note(note_ref, mode="outline")
            if found.get("found"):
                matches.append(
                    {
                        "vault_id": vault_dir.name,
                        "note_id": found.get("note_id", ""),
                        "path": found.get("path", ""),
                        "ref": f"{vault_dir.name}:{found.get('note_id', '')}",
                    }
                )
        return matches

    def _get_available_vaults(self) -> list[dict]:
        """Get structured information about available vaults.

        Returns:
            List of vault information dictionaries with vault_id, has_manifest, and has_index
        """
        vaults_dir = self.data_dir / "vaults"
        if not vaults_dir.exists():
            return []

        vault_dirs = [d for d in vaults_dir.iterdir() if d.is_dir()]
        vaults_info = []

        for vault_dir in sorted(vault_dirs):
            vault_id = vault_dir.name
            settings = self._build_settings(vault_id)
            if not self._is_displayable_vault(settings):
                continue
            vaults_info.append({
                "vault_id": vault_id,
                "has_manifest": settings.manifest_path.exists(),
                "has_index": settings.index_path.exists(),
            })

        return vaults_info

    def _is_displayable_vault(self, settings: VaultSettings) -> bool:
        if settings.manifest_path.exists():
            return True
        if settings.files_dir.exists() and any(settings.files_dir.rglob("*")):
            return True
        return self._index_has_notes(settings)

    def _index_has_notes(self, settings: VaultSettings) -> bool:
        if not settings.index_path.exists():
            return False
        import sqlite3

        conn = sqlite3.connect(settings.index_path)
        try:
            row = conn.execute("select count(*) from notes where vault_id = ?", (settings.vault_id,)).fetchone()
            return bool(row and row[0] > 0)
        except sqlite3.Error:
            return False
        finally:
            conn.close()

    def _status_text(self) -> str:
        vaults_dir = self.data_dir / "vaults"
        if not vaults_dir.exists():
            return "NoteSift 状态：未初始化"

        lines = ["NoteSift 状态"]
        lines.append(f"数据目录: {self.data_dir}")

        vaults_info = self._get_available_vaults()
        if not vaults_info:
            lines.append("未找到知识库")
            return "\n".join(lines)

        for vault in vaults_info:
            vault_id = vault["vault_id"]
            settings = self._build_settings(vault_id)

            lines.append(f"\n[{vault_id}]")
            lines.append(f"  manifest: {'存在' if vault['has_manifest'] else '不存在'}")
            lines.append(f"  index: {'存在' if vault['has_index'] else '不存在'}")
            lines.append(f"  files: {settings.files_dir}")

        return "\n".join(lines)

    async def page_get_vaults(self):
        """Web API: Get all vaults with status and file count."""
        from quart import jsonify
        import json

        vaults_info = self._get_available_vaults()

        # Enrich with file count and name from manifest
        for vault in vaults_info:
            vault_id = vault["vault_id"]
            settings = self._build_settings(vault_id)

            # Try to read file count and name from manifest
            file_count = 0
            vault_name = vault_id  # Default to vault_id
            imported_at = None

            if settings.manifest_path.exists():
                try:
                    manifest_data = json.loads(settings.manifest_path.read_text(encoding="utf-8"))
                    file_count = manifest_data.get("file_count", 0)
                    vault_name = manifest_data.get("vault_name", vault_id)
                    imported_at = manifest_data.get("imported_at") or imported_at_from_import_id(
                        manifest_data.get("import_id")
                    )
                except Exception:
                    pass

            vault["file_count"] = file_count
            vault["name"] = vault_name
            vault["imported_at"] = imported_at

        return jsonify({"vaults": vaults_info})

    async def page_import_vault(self):
        """Web API: upload and import a vault zip."""
        from quart import jsonify, request
        import base64

        upload_dir = self.data_dir / "tmp_uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)

        zip_path = None
        vault_id = ""
        try:
            content_type = request.content_type or ""
            if "multipart/form-data" in content_type:
                files = await request.files
                form = await request.form
                file = files.get("file")
                if file is None:
                    return jsonify({"success": False, "error": "缺少 zip 文件"}), 400
                filename = Path(file.filename or "vault.zip").name
                if Path(filename).suffix.lower() != ".zip":
                    return jsonify({"success": False, "error": "仅支持 zip 文件"}), 400
                vault_id = str(form.get("vault_id", "")).strip()
                zip_path = upload_dir / filename
                await file.save(zip_path)
            else:
                data = await request.get_json()
                if not isinstance(data, dict):
                    return jsonify({"success": False, "error": "请求体无效"}), 400
                filename = Path(str(data.get("filename") or "vault.zip")).name
                if Path(filename).suffix.lower() != ".zip":
                    return jsonify({"success": False, "error": "仅支持 zip 文件"}), 400
                encoded = str(data.get("content_base64") or "")
                if not encoded:
                    return jsonify({"success": False, "error": "缺少 zip 文件内容"}), 400
                vault_id = str(data.get("vault_id") or "").strip()
                zip_path = upload_dir / filename
                zip_path.write_bytes(base64.b64decode(encoded))

            resolved_vault_id = self._resolve_upload_vault_id(vault_id, zip_path)
            settings = self._build_settings(resolved_vault_id)
            manifest = VaultImporter(settings).import_zip(zip_path)
            return jsonify({"success": True, "manifest": manifest_summary(manifest)})
        except (ValueError, ImportErrorInfo) as error:
            if zip_path and zip_path.exists():
                zip_path.unlink(missing_ok=True)
            return jsonify({"success": False, "error": str(error)}), 400
        except Exception as error:
            if zip_path and zip_path.exists():
                zip_path.unlink(missing_ok=True)
            logger.error(f"Failed to import vault from page: {error}")
            return jsonify({"success": False, "error": "导入失败"}), 500

    async def page_rebuild_vault(self):
        """Web API: rebuild a vault index from existing files."""
        from quart import jsonify, request

        data = await request.get_json()
        vault_id = str((data or {}).get("vault_id") or "").strip()
        try:
            self._validate_vault_id(vault_id)
            manifest = VaultImporter(self._build_settings(vault_id)).rebuild_from_files()
            return jsonify({"success": True, "manifest": manifest_summary(manifest)})
        except (ValueError, ImportErrorInfo) as error:
            return jsonify({"success": False, "error": str(error)}), 400

    async def page_delete_vault(self, vault_id: str):
        """Web API: delete a vault data directory."""
        from quart import jsonify

        try:
            self._delete_vault_data(vault_id)
            return jsonify({"success": True, "vault_id": vault_id})
        except ValueError as error:
            return jsonify({"success": False, "error": str(error)}), 400

    async def page_delete_vault_post(self):
        """Web API: delete a vault via POST for page bridge compatibility."""
        from quart import jsonify, request

        data = await request.get_json()
        vault_id = str((data or {}).get("vault_id") or "").strip()
        try:
            self._delete_vault_data(vault_id)
            return jsonify({"success": True, "vault_id": vault_id})
        except ValueError as error:
            return jsonify({"success": False, "error": str(error)}), 400

    def _resolve_upload_vault_id(self, vault_id: str, zip_path: Path) -> str:
        resolved = vault_id.strip() or extract_vault_id_from_path(zip_path)
        self._validate_vault_id(resolved)
        return resolved

    def _validate_vault_id(self, vault_id: str) -> None:
        if not vault_id:
            raise ValueError("vault_id 不能为空")
        if not re.fullmatch(r"[\w一-鿿-]+", vault_id):
            raise ValueError("vault_id 只能包含字母、数字、下划线、短横线或中文")
        if any(separator in vault_id for separator in ("/", "\\")) or ".." in vault_id:
            raise ValueError("vault_id 包含非法路径字符")

    def _delete_vault_data(self, vault_id: str) -> None:
        self._validate_vault_id(vault_id)
        vaults_dir = (self.data_dir / "vaults").resolve()
        target = (vaults_dir / vault_id).resolve()
        if target == vaults_dir or vaults_dir not in target.parents:
            raise ValueError("vault_id 指向非法目录")
        if not target.exists():
            raise ValueError(f"知识库不存在: {vault_id}")
        shutil.rmtree(target)

    def _sanitize_config_update(self, data: Any) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise ValueError("请求体无效")
        result: dict[str, Any] = {}
        for key, value in data.items():
            if key in ("max_read_chars", "max_discover_snippet_chars", "compressed_section_preview_chars"):
                try:
                    parsed = int(value)
                except (TypeError, ValueError):
                    raise ValueError(f"{key} 必须为整数")
                if parsed <= 0:
                    raise ValueError(f"{key} 必须为正整数")
                result[key] = parsed
            elif key == "default_read_mode":
                if value not in READ_MODES:
                    raise ValueError(f"default_read_mode 必须是 {READ_MODES} 之一")
                result[key] = value
            elif key == "full_over_limit_strategy":
                if value not in OVER_LIMIT_STRATEGIES:
                    raise ValueError(f"full_over_limit_strategy 必须是 {OVER_LIMIT_STRATEGIES} 之一")
                result[key] = value
            elif key == "enable_acl":
                result[key] = bool(value)
            elif key == "allowed_sessions":
                result[key] = str(value)
            # 其余未知 key 一律忽略
        return result

    async def page_config(self):
        """Web API: Get or update plugin config."""
        from quart import jsonify, request

        if request.method == "GET":
            config = {
                "max_discover_snippet_chars": self.config.get("max_discover_snippet_chars", 300),
                "default_read_mode": self.config.get("default_read_mode", "outline"),
                "max_read_chars": self.config.get("max_read_chars", 8000),
                "full_over_limit_strategy": self.config.get("full_over_limit_strategy", "strict"),
                "compressed_section_preview_chars": self.config.get("compressed_section_preview_chars", 200),
                "enable_acl": self.config.get("enable_acl", False),
                "allowed_sessions": self.config.get("allowed_sessions", "")
            }
            return jsonify(config)

        elif request.method == "POST":
            data = await request.get_json()
            try:
                sanitized = self._sanitize_config_update(data)
            except ValueError as error:
                return jsonify({"success": False, "error": str(error)}), 400

            for key, value in sanitized.items():
                self.config[key] = value

            try:
                if hasattr(self.config, 'save_config'):
                    self.config.save_config()
                elif hasattr(self.config, 'save'):
                    self.config.save()
            except Exception as e:
                logger.warning(f"Failed to save config: {e}")

            return jsonify({"success": True, "message": "配置已保存", "applied": sorted(sanitized)})


def parse_allowed_sessions(value: Any) -> set[str]:
    if isinstance(value, list):
        return {str(item).strip() for item in value if str(item).strip()}
    if isinstance(value, str):
        return {line.strip() for line in value.splitlines() if line.strip()}
    return set()


def render_search_results(results: list[dict[str, Any]]) -> str:
    if not results:
        return "未找到相关笔记。"
    lines = ["知识库候选笔记："]
    for index, item in enumerate(results, start=1):
        vault_label = f"[{item['vault_id']}] " if item.get("vault_id") else ""
        lines.append(f"{index}. {vault_label}{item['title']} | {item['path']}")
        lines.append(f"   命中: {', '.join(item['matched_fields'])} | score={item['score']}")
        if item.get("tags"):
            lines.append(f"   tags: {', '.join(item['tags'])}")
        if item.get("aliases"):
            lines.append(f"   aliases: {', '.join(item['aliases'])}")
        for snippet in item.get("snippets", []):
            lines.append(f"   snippet: {snippet}")
    return "\n".join(lines)


def render_read_result(result: dict[str, Any]) -> str:
    if not result.get("found"):
        return f"读取失败：{result.get('error', 'not found')}"
    lines = [f"# {result['title']}", result["path"]]
    if result.get("tags"):
        lines.append(f"tags: {', '.join(result['tags'])}")
    if result.get("aliases"):
        lines.append(f"aliases: {', '.join(result['aliases'])}")

    # Show pagination info if present
    if result.get("page_info"):
        page_info = result["page_info"]
        lines.append(f"页 {page_info['current']}/{page_info['total']}")
        if page_info.get("has_next"):
            lines.append("提示: 使用 page 参数读取下一页")

    if result.get("truncated"):
        lines.append("内容超过单次读取上限。可按 heading 使用 section 模式继续读取。")

    content = result.get("content") or ""
    if content:
        lines.append("")
        lines.append(content)
    elif result.get("headings"):
        lines.append("")
        lines.append("Headings:")
        for heading in result["headings"]:
            lines.append(f"{'  ' * max(0, heading['level'] - 1)}- {heading['title']}")
    return "\n".join(lines)


def render_grep_results(results: list[dict[str, Any]]) -> str:
    if not results:
        return "未找到正文命中。"
    lines = ["正文命中片段："]
    for index, item in enumerate(results, start=1):
        lines.append(f"{index}. {item['title']} | {item['path']}")
        lines.append(item["snippet"])
    return "\n".join(lines)


def format_tool_payload(payload: Any) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, indent=2)


def format_discover_results(results: list[dict[str, Any]], verbose: bool = False) -> list[dict[str, Any]]:
    formatted = []
    for rank, item in enumerate(results, start=1):
        vault_id = item.get("vault_id", "")
        note_id = item.get("note_id", "")
        output = {
            "rank": rank,
            "ref": f"{vault_id}:{note_id}" if vault_id and note_id else note_id,
            "vault_id": vault_id,
            "note_id": note_id,
            "path": item.get("path", ""),
            "title": item.get("title", ""),
            "matched": item.get("matched_fields", []),
        }
        snippets = [snippet for snippet in item.get("snippets", []) if snippet]
        if snippets:
            output["snippets"] = snippets
        if verbose:
            output["score"] = item.get("score", 0)
            output["tags"] = item.get("tags", [])
            output["aliases"] = item.get("aliases", [])
        formatted.append(output)
    return formatted


def format_read_result(result: dict[str, Any], vault_id: str, mode: str, verbose: bool = False) -> dict[str, Any]:
    if not result.get("found") and not result.get("note_id"):
        return result

    note_id = result.get("note_id", "")
    output = {
        "found": bool(result.get("found")),
        "ref": f"{vault_id}:{note_id}" if vault_id and note_id else note_id,
        "vault_id": vault_id,
        "note_id": note_id,
        "path": result.get("path", ""),
        "title": result.get("title", ""),
        "mode": mode,
    }

    content = result.get("content")
    if content:
        output["content"] = content
    if mode == "outline" or result.get("truncated"):
        headings = result.get("headings", [])
        if result.get("truncated") and mode == "full":
            headings = compact_headings(headings)
        if headings:
            output["headings"] = headings
    if mode == "section":
        if "heading" in result:
            output["heading"] = result.get("heading")
        if "heading_matched" in result:
            output["heading_matched"] = result.get("heading_matched")
        if result.get("requested_heading"):
            output["requested_heading"] = result["requested_heading"]
        if result.get("available_headings") is not None:
            output["available_headings"] = compact_headings(result.get("available_headings", []))
    if mode == "snippets" and result.get("content"):
        output["query"] = result.get("query", "")
    if result.get("page_info"):
        output["page_info"] = result["page_info"]
    if result.get("truncated"):
        output["truncated"] = True
    if result.get("next_action_hint"):
        output["next_action_hint"] = result["next_action_hint"]
    if result.get("error"):
        output["error"] = result["error"]
    if verbose:
        output["tags"] = result.get("tags", [])
        output["aliases"] = result.get("aliases", [])

    return output


def compact_headings(headings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [heading for heading in headings if heading.get("level", 0) <= 3]


def manifest_summary(manifest: Any) -> dict[str, Any]:
    return {
        "import_id": manifest.import_id,
        "vault_id": manifest.vault_id,
        "file_count": manifest.file_count,
        "ignored_count": manifest.ignored_count,
        "imported_at": manifest.imported_at,
        "vault_root": manifest.vault_root,
    }


def imported_at_from_import_id(import_id: Any) -> str | None:
    try:
        timestamp_ms = int(import_id)
    except (TypeError, ValueError):
        return None
    if timestamp_ms <= 0:
        return None
    from datetime import datetime, timezone

    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).replace(microsecond=0).isoformat()


def validate_int_param(value: Any, default: int, min_val: int = None, max_val: int = None) -> int:
    """Validate and sanitize integer parameters from LLM tool calls.

    Args:
        value: Input value (could be int, str, None, etc.)
        default: Default value if parsing fails
        min_val: Minimum allowed value (optional)
        max_val: Maximum allowed value (optional)

    Returns:
        Validated integer within range
    """
    # Handle None or empty string
    if value is None or value == "":
        return default

    # Try to parse as int
    try:
        result = int(value)
    except (ValueError, TypeError):
        return default

    # Apply min/max constraints
    if min_val is not None:
        result = max(min_val, result)
    if max_val is not None:
        result = min(max_val, result)

    return result
