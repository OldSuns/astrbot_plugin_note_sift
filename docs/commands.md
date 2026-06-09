# 命令使用

本文档详细说明 NoteSift 插件的所有命令。

## 命令列表

- `/kb search` - 搜索知识库
- `/kb read` - 读取笔记
- `/kb grep` - 正文搜索
- `/kb status` - 查看状态
- `/kb rebuild` - 重建索引（管理员）

## /kb search

搜索知识库中的候选笔记。

### 语法

```bash
/kb search <query>
```

### 查询格式

**普通搜索**（搜索 default 库）：
```bash
/kb search 川崎病
```

**指定库搜索**：
```bash
/kb search medical:川崎病
/kb search tech:async programming
```

**多词查询**（所有词都必须存在）：
```bash
/kb search 川崎病 IVIG 治疗
```

### 搜索范围

搜索以下字段（按权重排序）：
1. 标题（权重 100）
2. 别名（权重 80）
3. 标签（权重 70）
4. 路径（权重 60）
5. 标题层级（权重 50）
6. 正文（权重 10）

### 返回格式

```
知识库候选笔记：
1. [medical] 川崎病 | cardiology/kawasaki.md
   命中: title, tags | score=170
   tags: 儿科学, 心血管
   snippet: IVIG 是川崎病的主要治疗方法...

2. [medical] 川崎病诊断标准 | cardiology/kd_diagnosis.md
   命中: title, body | score=110
   snippet: 川崎病的诊断需要满足以下条件...
```

### 使用提示

- 搜索结果编号可用于后续 `/kb read` 命令
- 结果按匹配分数排序
- 仅命中正文时显示片段
- 最多返回 8 条结果

### 示例

```bash
# 搜索疾病
/kb search 心血管疾病

# 跨库搜索特定内容
/kb search medical:IVIG治疗

# 搜索技术文档
/kb search tech:async await

# 多词精确查询
/kb search 川崎病 阿司匹林 治疗方案
```

## /kb read

读取指定笔记的内容。

### 语法

```bash
/kb read <note_ref> [mode] [page]
```

### 参数说明

**note_ref**（必填）：
- `1` - 搜索结果编号
- `medical:cardiology.md` - vault_id:路径
- `tech:note_abc123` - vault_id:note_id
- `note.md` - 在 default 库中查找

**mode**（可选）：
- `outline` - 元数据 + 标题树（默认）
- `summary` - 摘要标注
- `section` - 指定章节
- `snippets` - 查询片段
- `full` - 完整正文

**page**（可选）：
- 仅在 paged 模式下有效
- 页码，从 1 开始

### 返回格式

**outline 模式**：
```
# 川崎病
cardiology/kawasaki.md
tags: 儿科学, 心血管
aliases: KD

Headings:
- 川崎病
  - 病因
  - 症状
  - 诊断
  - 治疗
    - IVIG 治疗
    - 阿司匹林治疗
```

**full 模式（paged）**：
```
# 川崎病
cardiology/kawasaki.md
页 1/3
提示: 使用 page 参数读取下一页

川崎病（Kawasaki disease, KD）是一种...
（第一页内容）
```

**full 模式（compressed）**：
```
# 川崎病

川崎病（Kawasaki disease, KD）是一种以全身血管炎为主要病理的...

## 病因

目前病因尚不明确，可能与感染、免疫异常等因素有关...

## 症状

主要症状包括：持续发热、结膜充血、口唇皲裂...

（每节仅显示前 N 字符）
```

### 使用提示

- 优先使用 `outline` 了解结构
- 长文档建议先用 `outline` 再用 `section`
- paged 模式适合完整阅读
- compressed 模式适合快速预览

### 示例

```bash
# 读取搜索结果第 1 条的大纲
/kb read 1

# 读取完整内容（第 1 页）
/kb read 1 full

# 读取第 2 页
/kb read 1 full 2

# 跨库读取
/kb read medical:kawasaki.md full

# 读取指定笔记的大纲
/kb read tech:python_async.md outline
```

## /kb grep

在笔记正文中搜索并返回命中片段。

### 语法

```bash
/kb grep <query>
```

### 查询格式

**普通搜索**（搜索 default 库）：
```bash
/kb grep 关键词
```

**指定库搜索**：
```bash
/kb grep medical:阿司匹林
/kb grep tech:async/await
```

### 返回格式

```
正文命中片段：
1. 川崎病治疗 | treatment.md
阿司匹林作为抗血小板药物，在川崎病治疗中起重要作用...

2. 药物相互作用 | drug_interactions.md
阿司匹林与其他 NSAIDs 药物可能产生相互作用...
```

### 与 search 的区别

| 特性 | search | grep |
|------|--------|------|
| 搜索范围 | 标题、标签、别名、正文 | 仅正文 |
| 返回内容 | 元数据 + 可选片段 | 必定返回片段 |
| 排序方式 | 按匹配分数 | 按文档顺序 |
| 适用场景 | 发现候选笔记 | 精确查找内容 |

### 示例

```bash
# 搜索治疗方法
/kb grep IVIG治疗

# 在技术库中搜索代码
/kb grep tech:async def

# 搜索特定药物
/kb grep medical:阿司匹林剂量
```

## /kb status

查看所有知识库的导入和索引状态。

### 语法

```bash
/kb status
```

### 返回格式

```
NoteSift 状态
数据目录: /data/astrbot/plugin_data/note_sift

[medical]
  manifest: 存在
  index: 存在
  files: /data/astrbot/plugin_data/note_sift/vaults/medical/files

[tech]
  manifest: 存在
  index: 存在
  files: /data/astrbot/plugin_data/note_sift/vaults/tech/files

[default]
  manifest: 不存在
  index: 不存在
  files: /data/astrbot/plugin_data/note_sift/vaults/default/files
```

### 状态说明

- **manifest 存在**：知识库已成功导入
- **index 存在**：索引数据库已创建
- **files**：文件存储路径

### 使用场景

- 检查知识库是否导入成功
- 查看数据存储位置
- 排查导入问题

## /kb rebuild

管理员命令：从已导入的 files 目录重建知识库索引。

### 语法

```bash
/kb rebuild [vault_id]
```

### 参数说明

- 不指定 vault_id：重建所有已导入的知识库
- 指定 vault_id：仅重建指定的知识库

### 返回格式

```
重建完成：
medical: 152 个文件，FTS5可用
tech: 87 个文件，FTS5可用
```

### 使用场景

- 索引损坏需要修复
- 配置变更后重建索引
- 插件升级后重建索引
- FTS5 可用性变化

### 工作原理

1. 扫描已导入的 `files/` 目录
2. 重新解析所有 Markdown 文件
3. 重建 SQLite 索引
4. **不需要原始 zip 文件**

### 注意事项

- ⚠️ 重建会替换现有索引
- ⚠️ 重建期间知识库暂不可用
- ✓ 不需要重新上传 zip 文件
- ✓ files 目录内容不受影响

### 示例

```bash
# 重建所有知识库
/kb rebuild

# 重建 medical 知识库
/kb rebuild medical

# 重建 tech 知识库
/kb rebuild tech
```

## 命令权限

| 命令 | 权限要求 | ACL 控制 |
|------|----------|---------|
| search | 普通用户 | ✓ |
| read | 普通用户 | ✓ |
| grep | 普通用户 | ✓ |
| status | 普通用户 | ✓ |
| rebuild | 管理员 | ✗ |

**说明**：
- ACL 控制：受 `enable_acl` 和 `allowed_sessions` 配置影响
- rebuild 命令：需要 AstrBot 管理员权限，不受 ACL 影响

## 命令组合使用

### 场景 1：快速查找和阅读

```bash
# 1. 搜索候选
/kb search 川崎病治疗

# 2. 查看大纲
/kb read 1 outline

# 3. 读取完整内容
/kb read 1 full
```

### 场景 2：跨库查找特定内容

```bash
# 1. 在医学库搜索
/kb search medical:IVIG

# 2. 在技术库搜索
/kb search tech:async

# 3. 比对结果
```

### 场景 3：精确定位内容

```bash
# 1. 搜索笔记
/kb search 药物治疗

# 2. 在正文中精确查找
/kb grep 阿司匹林剂量

# 3. 读取命中的笔记
/kb read 1 full
```

### 场景 4：长文档浏览

```bash
# 1. 搜索文档
/kb search Python教程

# 2. 查看大纲
/kb read 1 outline

# 3. 分页阅读
/kb read 1 full 1
/kb read 1 full 2
/kb read 1 full 3
```

## 命令快捷技巧

### 1. 使用搜索结果编号

搜索后直接用编号读取，无需记住 note_id：

```bash
/kb search 川崎病
/kb read 1    # 直接用编号
```

### 2. 跨库前缀语法

使用 `vault_id:` 前缀快速指定知识库：

```bash
/kb search medical:疾病
/kb grep tech:代码示例
/kb read medical:note.md
```

### 3. 渐进式阅读

从大纲到详细，逐步深入：

```bash
/kb read 1 outline     # 了解结构
/kb read 1 summary     # 看要点
/kb read 1 full        # 读详细
```

## 常见问题

### Q: 搜索结果编号在新会话中还能用吗？

A: 不能。搜索结果编号仅在当前会话有效。新会话需要重新搜索。

### Q: 如何搜索所有知识库？

A: 命令行搜索默认仅搜索 default 库。需要分别搜索各库，或使用 LLM 工具进行跨库搜索。

### Q: paged 模式如何知道总页数？

A: 读取任意页时都会显示页码信息，如 "页 1/3"。

### Q: 如何知道有哪些知识库？

A: 使用 `/kb status` 命令查看所有已配置的知识库。

### Q: 命令支持正则表达式吗？

A: 命令行不支持。正则搜索需通过 LLM 工具调用（`regex=true` 参数）。
