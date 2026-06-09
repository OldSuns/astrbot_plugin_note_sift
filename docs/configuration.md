# 配置指南

本文档详细说明 NoteSift 插件的所有配置项。

## 配置文件格式

配置通过 AstrBot 插件配置页面设置，格式为 JSON。

## 完整配置示例

```json
{
  "vault_zip": [],
  "full_over_limit_strategy": "paged",
  "compressed_section_preview_chars": 200,
  "max_read_chars": 8000,
  "max_discover_snippet_chars": 300,
  "enable_acl": false,
  "allowed_sessions": "",
  "default_read_mode": "outline"
}
```

## 知识库配置

### vault_zip（必填）

通过插件配置页面上传知识库 zip 文件。

**使用方法**：
1. 在插件配置页面点击"上传 zip 文件"按钮
2. 选择知识库 zip 文件
3. 可重复上传多个 zip 文件
4. 保存配置后，插件自动导入

**说明**：
- 自动从文件名提取 vault_id
- 例：`medical.zip` → vault_id 为 `medical`
- 特殊字符自动替换：`儿科学-2024.zip` → `儿科学_2024`
- zip 导入成功后会被自动删除（内容已解压到数据目录）

### 数据存储

数据自动存储在 `AstrBot 数据目录/plugin_data/astrbot_plugin_note_sift/` 下。

**目录结构**：
```
plugin_data/astrbot_plugin_note_sift/
  vaults/
    medical/
      files/           # 解压后的笔记文件
      index.sqlite3    # SQLite 索引数据库
      import_manifest.json  # 导入清单
    tech/
      files/
      index.sqlite3
      import_manifest.json
```

## 读取策略配置

### full_over_limit_strategy

当内容超过 `max_read_chars` 时的处理策略。

**默认值**：`"strict"`

**可选值**：
- `"strict"`：拒绝返回正文，仅返回标题树和提示
- `"paged"`：在段落边界自动分页，返回分页信息
- `"compressed"`：返回结构化骨架（所有标题 + 每节预览）

**使用建议**：
- 严格控制：使用 `strict`
- 需要完整浏览：使用 `paged`
- 快速预览长文档：使用 `compressed`

### compressed_section_preview_chars

压缩模式下每个章节的预览字符数。

**默认值**：`200`

**类型**：整数

**说明**：
- 仅在 `full_over_limit_strategy = "compressed"` 时生效
- 值越大，预览内容越多，但总体积也越大
- 建议范围：100-500

**示例**：
```json
{
  "full_over_limit_strategy": "compressed",
  "compressed_section_preview_chars": 150
}
```

### max_read_chars

单次读取的最大字符数。

**默认值**：`8000`

**类型**：整数

**说明**：
- 在 `paged` 模式下同时作为每页的大小
- 在 `strict` 模式下作为拒绝阈值
- 建议根据 LLM 上下文窗口大小调整

**示例**：
```json
{
  "max_read_chars": 10000
}
```

### max_discover_snippet_chars

搜索发现阶段单条正文片段的最大字符数。

**默认值**：`300`

**类型**：整数

**说明**：
- 仅在搜索命中正文时返回片段
- 用于快速预览命中内容
- 不影响实际读取

### default_read_mode

手动 `/kb read` 命令的默认读取模式。

**默认值**：`"outline"`

**可选值**：`outline`、`summary`、`section`、`snippets`、`full`

**说明**：
- 仅影响手动命令，不影响 LLM 工具调用
- 建议使用 `outline` 以避免意外加载大量内容

## 访问控制配置

### enable_acl

是否启用会话白名单。

**默认值**：`false`

**类型**：布尔值

**说明**：
- `true`：仅白名单中的会话可访问
- `false`：所有会话都可访问
- 插件级别控制，不区分具体知识库

### allowed_sessions

允许访问知识库的 unified_msg_origin，每行一个。

**默认值**：空字符串

**类型**：文本（多行）

**格式**：
```
platform_session1
platform_session2
platform_session3
```

**说明**：
- 仅在 `enable_acl = true` 时生效
- 每行一个 UMO（unified_msg_origin）
- 空行会被忽略

**示例**：
```json
{
  "enable_acl": true,
  "allowed_sessions": "qq_12345\nwechat_67890"
}
```

## 其他配置

### show_sources_in_answer

提示模型在最终回答中展示来源。

**默认值**：`false`

**类型**：布尔值

**说明**：
- 当前版本工具始终返回来源
- 此项为未来提示策略预留
- 暂不影响实际行为

## 配置最佳实践

### 1. 按场景选择策略

**快速查询场景**：
```json
{
  "full_over_limit_strategy": "strict",
  "default_read_mode": "outline"
}
```

**深度阅读场景**：
```json
{
  "full_over_limit_strategy": "paged",
  "max_read_chars": 10000
}
```

**预览浏览场景**：
```json
{
  "full_over_limit_strategy": "compressed",
  "compressed_section_preview_chars": 200
}
```

### 2. 根据 LLM 窗口调整

**小窗口模型（4K-8K）**：
```json
{
  "max_read_chars": 4000,
  "max_discover_snippet_chars": 200
}
```

**大窗口模型（32K+）**：
```json
{
  "max_read_chars": 15000,
  "max_discover_snippet_chars": 500
}
```

### 3. 多知识库组织

**按领域分类**：
```json
{
  "vaults": [
    {"id": "medical", "path": "/data/medical.zip"},
    {"id": "legal", "path": "/data/legal.zip"},
    {"id": "tech", "path": "/data/tech.zip"}
  ]
}
```

**按项目分类**：
```json
{
  "vaults": [
    {"id": "project_a", "path": "/data/project_a.zip"},
    {"id": "project_b", "path": "/data/project_b.zip"}
  ]
}
```

## 配置验证

配置完成后，可以通过以下命令验证：

```bash
# 查看所有知识库状态
/kb status

# 测试搜索
/kb search test

# 测试读取
/kb read 1 outline
```

## 常见配置问题

### 1. 知识库导入失败

**检查项**：
- zip 文件路径是否正确
- 文件权限是否可读
- zip 中是否包含支持的文件类型（.md, .markdown, .txt）

### 2. 搜索结果为空

**检查项**：
- 确认知识库已成功导入（`/kb status`）
- 检查 vault_id 是否正确
- 确认搜索词存在于笔记中

### 3. 内容被截断

**解决方案**：
- 增加 `max_read_chars` 值
- 或使用 `paged` 模式
- 或使用 `section` 模式读取特定章节

### 4. ACL 不生效

**检查项**：
- 确认 `enable_acl` 为 `true`
- 检查 `allowed_sessions` 格式是否正确
- 确认 UMO 与实际会话匹配

## 配置示例集

### 示例 1：个人笔记本

```json
{
  "vaults": [
    {"path": "/home/user/notes.zip"}
  ],
  "full_over_limit_strategy": "paged",
  "max_read_chars": 8000,
  "enable_acl": false
}
```

### 示例 2：团队知识库

```json
{
  "vaults": [
    {"id": "technical", "path": "/data/tech.zip"},
    {"id": "business", "path": "/data/biz.zip"}
  ],
  "full_over_limit_strategy": "compressed",
  "compressed_section_preview_chars": 200,
  "enable_acl": true,
  "allowed_sessions": "team_member_1\nteam_member_2"
}
```

### 示例 3：教育场景

```json
{
  "vaults": [
    {"id": "math", "path": "/courses/math.zip"},
    {"id": "physics", "path": "/courses/physics.zip"},
    {"id": "chemistry", "path": "/courses/chemistry.zip"}
  ],
  "full_over_limit_strategy": "paged",
  "max_read_chars": 6000,
  "default_read_mode": "outline"
}
```
