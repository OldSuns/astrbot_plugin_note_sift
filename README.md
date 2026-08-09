# NoteSift / 筛记

<img src="https://count.getloli.com/get/@NoteSift?theme=moebooru" alt="Moe Counter">

![AstrBot Plugin](https://img.shields.io/badge/AstrBot-Plugin-5865F2)
![Search](https://img.shields.io/badge/Search-SQLite%20LIKE%2FRegex-0F766E)
![License](https://img.shields.io/badge/license-MIT-blue)

面向 AstrBot 的 Grep-first Markdown/Obsidian 知识库插件。

## 文档导航

| 文档 | 内容 |
|------|------|
| [命令使用](docs/commands.md) | `/kb search`、`/kb read`、`/kb grep`、`/kb status`、`/kb rebuild` |
| [配置指南](docs/configuration.md) | 配置项、数据目录、ACL、导入与读取参数 |
| [LLM 工具接口](docs/llm-tools.md) | `kb_discover`、`kb_read` 的参数、输出与调用建议 |
| [多知识库](docs/multi-vault.md) | 多 vault 架构、`vault_id`、跨库搜索与管理 |
| [读取模式](docs/read-modes.md) | `outline`、`summary`、`section`、`snippets`、`full` |
| [使用场景](docs/use-cases.md) | 常见工作流和最佳实践示例 |
| [故障排除](docs/troubleshooting.md) | 导入、搜索、读取、权限等常见问题 |

## 核心特性

- **多知识库管理** — 支持导入和管理多个独立知识库
- **Dashboard 页面** — 可视化控制面板，实时查看所有知识库状态
- **智能文件提取** — 自动过滤，仅提取 Markdown/文本文件
- **安全检查** — 严格的 zip 安全检查，防止路径遍历
- **全文搜索** — 基于 SQLite 子串/正则的多字段加权搜索（标题/别名/标签/路径/正文），跨字段词覆盖
- **渐进式阅读** — 先搜索发现，再按需读取
- **五种读取模式**
  - `outline` — 元数据 + 标题树
  - `summary` — 提取标注块（[!summary]/[!note]/[!tip] 等），无标注时回退前导段落
  - `section` — 按标题读取指定章节
  - `snippets` — 查询相关正文片段
  - `full` — 完整正文（支持 strict/paged/compressed 三种超限策略）
- **LLM 工具** — 提供 `kb_list_vaults`、`kb_discover`、`kb_read` 和 `kb_related` 函数工具
- **跨库搜索** — 单次搜索覆盖所有或指定知识库
- **Obsidian 自动识别** — 自动检测 `.obsidian` 目录并提取 vault 根路径
- **前置元数据解析** — 自动提取 tags、aliases，并解析双链供 `kb_related` 查询
- **访问控制** — 可选的会话白名单 ACL

## 安装

在 AstrBot 插件市场搜索 **NoteSift**，或手动克隆到插件目录。

## Dashboard 页面

插件提供可视化控制面板，在 AstrBot WebUI 的插件详情页中点击进入。

**当前功能**：
- 实时查看所有知识库状态（文件数、索引状态）
- 统计概览（知识库总数、文件总数、已索引库数）
- 快速搜索知识库
- Vault 管理：zip 上传导入、重建索引、删除知识库
- 设置页面：可视化配置管理

**计划中功能**：
- 文件浏览、搜索预览和导入历史

## 配置

插件配置文件 `_conf_schema.json` 定义以下配置项：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `vault_zip` | file | — | 上传知识库 zip 文件（可重复上传多个） |
| `enable_acl` | bool | `false` | 启用会话白名单 |
| `allowed_sessions` | text | — | 允许访问的 UMO，每行一个 |
| `default_read_mode` | string | `outline` | 默认读取模式 |
| `full_over_limit_strategy` | string | `strict` | 内容超限策略：strict / paged / compressed |
| `compressed_section_preview_chars` | int | `200` | 压缩模式每节预览字符数 |
| `max_read_chars` | int | `8000` | 单次读取最大字符数 |
| `max_discover_snippet_chars` | int | `300` | 搜索片段最大字符数 |

### 数据目录

数据自动存储在 `AstrBot 数据目录/plugin_data/astrbot_plugin_note_sift/` 下，目录结构：

```
plugin_data/astrbot_plugin_note_sift/
  vaults/
    default/
      files/           # 解压后的笔记文件
      index.sqlite3    # SQLite 索引数据库
      import_manifest.json  # 导入清单
    medical/
      files/
      index.sqlite3
      import_manifest.json
```

## 命令

| 命令 | 权限 | ACL | 说明 |
|------|------|-----|------|
| `/kb search <query>` | 普通 | ✓ | 搜索知识库候选笔记 |
| `/kb read <note_ref> [mode] [page]` | 普通 | ✓ | 读取笔记内容 |
| `/kb grep <query>` | 普通 | ✓ | 正文搜索并返回命中片段 |
| `/kb status` | 普通 | ✓ | 查看所有知识库状态 |
| `/kb rebuild [vault_id]` | 管理员 | ✗ | 从配置 zip 重建知识库 |

### 查询格式

支持 `vault_id:query` 前缀指定知识库：

```bash
/kb search 川崎病              # 搜索默认库
/kb search medical:川崎病       # 搜索 medical 库
/kb read 1                     # 读取搜索结果第 1 条
/kb read medical:kawasaki.md   # 按路径读取
/kb grep medical:阿司匹林        # 在 medical 库正文搜索
```

### 读取模式

| 模式 | 说明 | 适用场景 |
|------|------|---------|
| `outline` | 元数据 + 标题树 | 快速了解结构 |
| `summary` | 提取 callout 标注块 | 查看要点 |
| `section` | 读取指定章节（需 heading 参数） | 精确定位 |
| `snippets` | 查询相关片段（需 query 参数） | 关键信息查找 |
| `full` | 完整正文 | 详细阅读 |

### 全文超限策略

- **strict** — 内容超限时拒绝，仅返回标题树
- **paged** — 在段落边界自动分页，支持翻页
- **compressed** — 返回所有标题 + 每节预览

## LLM 工具

### kb_discover

```python
kb_discover(query="川崎病", limit=5, regex=false, vault_id="", verbose=false)
```

- `query` — 搜索关键词或正则表达式
- `limit` — 返回候选数量（默认 5，最大 10）
- `regex` — 是否按正则搜索
- `vault_id` — 指定知识库 ID，留空跨库搜索
- `verbose` — 是否返回 `score`、`tags`、`aliases` 等调试字段，默认关闭

默认返回精简字段，便于后续直接读取：

```json
{
  "results": [
    {
      "rank": 1,
      "ref": "medical:8f521aac31ee8784",
      "vault_id": "medical",
      "note_id": "8f521aac31ee8784",
      "path": "儿科学/川崎病.md",
      "title": "川崎病",
      "matched": ["title", "tags", "path"]
    }
  ]
}
```

`snippets` 只有非空时才返回；`verbose=true` 时额外返回 `score`、`tags`、`aliases`。

### kb_read

```python
kb_read(note_ref="medical:kawasaki.md", mode="outline", heading="", query="", page=1, vault_id="", verbose=false)
```

- `note_ref` — note_id 或路径
- `mode` — outline / summary / section / snippets / full
- `heading` — section 模式下的标题关键词
- `query` — snippets 模式下的检索词
- `page` — paged 模式下的页码
- `vault_id` — 指定知识库 ID，留空从 note_ref 前缀推断
- `verbose` — 是否返回 `tags`、`aliases` 等元数据，默认关闭

默认返回精简字段，并提供稳定读取引用 `ref`：

```json
{
  "found": true,
  "ref": "medical:8f521aac31ee8784",
  "vault_id": "medical",
  "note_id": "8f521aac31ee8784",
  "path": "儿科学/川崎病.md",
  "title": "川崎病",
  "mode": "outline",
  "headings": [
    {"level": 1, "title": "川崎病"},
    {"level": 2, "title": "治疗"}
  ]
}
```

`section` 模式会返回实际选中的标题：

```json
{
  "found": true,
  "ref": "medical:8f521aac31ee8784",
  "vault_id": "medical",
  "note_id": "8f521aac31ee8784",
  "path": "儿科学/川崎病.md",
  "title": "川崎病",
  "mode": "section",
  "heading": {"level": 2, "title": "治疗"},
  "content": "IVIG 是核心治疗。"
}
```

如果 `heading` 未命中，`section` 不会回退到第一个标题，而是返回可重试的错误报告；`available_headings` 只包含 `level <= 3` 的标题：

```json
{
  "found": false,
  "error": "heading not found",
  "ref": "medical:8f521aac31ee8784",
  "vault_id": "medical",
  "note_id": "8f521aac31ee8784",
  "path": "儿科学/川崎病.md",
  "title": "川崎病",
  "mode": "section",
  "requested_heading": "不存在的标题",
  "available_headings": [
    {"level": 1, "title": "川崎病"},
    {"level": 2, "title": "治疗"}
  ]
}
```

`full` 在 strict 策略下超限时不返回正文，只返回结构索引和 `truncated=true`；为控制工具输出长度，超限时的 `headings` 只包含 `level <= 3`，`outline` 模式仍返回完整标题树。

空字段不会输出；`truncated`、`next_action_hint` 只在需要时返回；`verbose=true` 时额外返回 `tags`、`aliases`。

### kb_related

```python
kb_related(note_ref="medical:kawasaki.md", vault_id="")
```

- `note_ref` — note_id 或路径，可用 `vault_id:note_ref` 前缀
- `vault_id` — 指定知识库 ID，留空则按前缀或跨库解析

返回该笔记的双链关系：`outlinks`（它链出的笔记，未解析的悬空链接标 `resolved:false`）与 `backlinks`（链入它的笔记）。解析范围限于同一知识库。

```json
{
  "found": true,
  "vault_id": "medical",
  "ref": "medical:8f521aac31ee8784",
  "note_id": "8f521aac31ee8784",
  "path": "儿科学/川崎病.md",
  "title": "川崎病",
  "outlinks": [{"ref": "medical:...", "note_id": "...", "path": "心血管/血管炎.md", "title": "血管炎", "resolved": true}],
  "backlinks": [{"ref": "medical:...", "note_id": "...", "path": "儿科学/发热鉴别.md", "title": "发热鉴别"}]
}
```

## 示例

### 医学知识查询

```bash
/kb search medical:川崎病
/kb read 1 outline
/kb read 1 full
```

### 长文档浏览

```bash
/kb read 1 outline       # 了解结构
/kb read 1 full 1        # 分页阅读
/kb read 1 full 2
```

## 注意事项

- 导入后 zip 文件会被自动删除，请提前备份
- Obsidian vault 自动检测：如包含 `.obsidian` 目录，仅导入该目录下内容
- 分页边界在段落：paged 模式在 `\n\n` 处分页，不截断段落

## 许可证

MIT License
