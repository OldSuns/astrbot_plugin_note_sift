# 多知识库

本文档详细说明 NoteSift 的多知识库架构和使用方法。

## 多知识库概念

NoteSift 支持同时管理多个独立的知识库，每个知识库有自己的：
- 独立的文件存储
- 独立的索引数据库
- 独立的导入记录
- 唯一的标识符（vault_id）

## 知识库 ID (vault_id)

### 生成规则

**1. 配置中明确指定**：
```json
{
  "vaults": [
    {"id": "medical", "path": "/data/medical.zip"}
  ]
}
```
vault_id = `"medical"`

**2. 从文件名自动提取**：
```json
{
  "vaults": [
    {"path": "/data/medical_vault.zip"}
  ]
}
```
vault_id = `"medical_vault"`（从文件名提取）

**3. 字符替换规则**：
- 保留：字母、数字、下划线、中文字符
- 替换为下划线：`-`、空格、其他特殊字符
- 去除首尾下划线

### 示例

| 文件名 | 生成的 vault_id |
|-------|----------------|
| `medical.zip` | `medical` |
| `medical-notes.zip` | `medical_notes` |
| `tech notes.zip` | `tech_notes` |
| `儿科学-2024.zip` | `儿科学_2024` |
| `project_a.zip` | `project_a` |

## 存储结构

每个知识库在数据目录下有独立的子目录：

```
data/
  vaults/
    default/                      # 默认知识库
      files/                      # 原始 Markdown 文件
        note1.md
        folder/
          note2.md
      index.sqlite3               # SQLite 索引
      import_manifest.json        # 导入记录
    
    medical/                      # 医学知识库
      files/
        cardiology/
          kawasaki.md
      index.sqlite3
      import_manifest.json
    
    tech/                         # 技术知识库
      files/
        python/
          async.md
      index.sqlite3
      import_manifest.json
```

### 文件说明

**files/**：
- 存储原始 Markdown 文件
- 保持原始目录结构
- 文件路径用于引用

**index.sqlite3**：
- SQLite 数据库
- 包含笔记索引和全文搜索
- 独立于其他库

**import_manifest.json**：
- 导入记录
- 包含文件数、zip 哈希等信息
- 用于状态查询

## 配置多知识库

### 基础配置

```json
{
  "vaults": [
    {
      "id": "medical",
      "path": "/data/medical_vault.zip"
    },
    {
      "id": "tech",
      "path": "/data/tech_notes.zip"
    },
    {
      "path": "/data/personal.zip"
    }
  ]
}
```

### 配置说明

- `id` 可选，省略时从文件名提取
- `path` 必填，指向 zip 文件
- 数组顺序不影响功能
- 可以随时添加新的知识库

### 更新配置

**添加新库**：
1. 在配置中上传新的 zip 文件
2. 保存配置
3. 重启插件自动导入

**删除库**：
1. 从配置中移除 vault 上传记录
2. 手动删除数据目录下的对应文件夹（可选）

**重建索引**：
```bash
/kb rebuild           # 重建所有库
/kb rebuild medical   # 重建指定库
```

## 跨库搜索

### 搜索模式

**1. 跨所有库搜索**（LLM 工具）：
```python
# 不指定 vault_id，搜索所有库
kb_discover("async programming")
```

**2. 指定库搜索**（LLM 工具）：
```python
# 仅搜索 medical 库
kb_discover("IVIG", vault_id="medical")
```

**3. 默认库搜索**（手动命令）：
```bash
# 不带前缀，搜索 default 库
/kb search keyword
```

**4. 指定库搜索**（手动命令）：
```bash
# 使用 vault_id: 前缀
/kb search medical:keyword
/kb search tech:async
```

### 搜索结果合并

跨库搜索时，结果会：
1. 从每个库获取结果
2. 为每个结果添加 `vault_id` 标记
3. 按 score 统一排序
4. 返回前 N 条

**示例**：
```json
{
  "results": [
    {
      "vault_id": "medical",
      "title": "川崎病",
      "score": 180,
      ...
    },
    {
      "vault_id": "tech",
      "title": "Async Programming",
      "score": 150,
      ...
    }
  ]
}
```

## 引用格式

### vault_id:reference 格式

在各种命令和工具中，可以使用 `vault_id:reference` 格式明确指定知识库：

**格式**：
- `vault_id:note_id` - 知识库 ID + 笔记 ID
- `vault_id:path` - 知识库 ID + 文件路径

**示例**：
```bash
# 命令行
/kb read medical:kawasaki.md
/kb read tech:python/async.md
/kb grep medical:阿司匹林

# LLM 工具
kb_read("medical:kawasaki.md", mode="full")
kb_read("tech:note_abc123", mode="outline")
```

### 搜索结果编号

搜索后可以直接使用编号，自动关联到结果中的 vault_id：

```bash
# 1. 搜索（可能跨多个库）
/kb search 异步编程

# 结果：
# 1. [tech] Python异步编程 | python/async.md
# 2. [js] JavaScript异步 | js/async.md

# 2. 使用编号读取（自动识别来源库）
/kb read 1    # 读取 tech 库的笔记
/kb read 2    # 读取 js 库的笔记
```

## 使用场景

### 场景 1：按领域分类

**组织方式**：
```json
{
  "vaults": [
    {"id": "medical", "path": "/data/medical.zip"},
    {"id": "legal", "path": "/data/legal.zip"},
    {"id": "tech", "path": "/data/tech.zip"},
    {"id": "business", "path": "/data/business.zip"}
  ]
}
```

**使用方式**：
```python
# 医学咨询
kb_discover("疾病治疗", vault_id="medical")

# 法律咨询
kb_discover("合同条款", vault_id="legal")

# 技术咨询
kb_discover("API设计", vault_id="tech")
```

### 场景 2：按项目分类

**组织方式**：
```json
{
  "vaults": [
    {"id": "project_a", "path": "/projects/a/docs.zip"},
    {"id": "project_b", "path": "/projects/b/docs.zip"},
    {"id": "shared", "path": "/shared/common.zip"}
  ]
}
```

**使用方式**：
```python
# 项目 A 相关
kb_discover("需求文档", vault_id="project_a")

# 项目 B 相关
kb_discover("API接口", vault_id="project_b")

# 通用知识
kb_discover("设计模式", vault_id="shared")
```

### 场景 3：按时间/版本分类

**组织方式**：
```json
{
  "vaults": [
    {"id": "docs_2024", "path": "/archive/docs_2024.zip"},
    {"id": "docs_2025", "path": "/archive/docs_2025.zip"},
    {"id": "docs_latest", "path": "/docs/current.zip"}
  ]
}
```

**使用方式**：
```python
# 查看最新文档
kb_discover("API文档", vault_id="docs_latest")

# 查看历史版本
kb_discover("API文档", vault_id="docs_2024")
```

### 场景 4：个人和团队知识库

**组织方式**：
```json
{
  "vaults": [
    {"id": "personal", "path": "/home/user/notes.zip"},
    {"id": "team", "path": "/shared/team_wiki.zip"},
    {"id": "company", "path": "/shared/company_kb.zip"}
  ]
}
```

**使用方式**：
```python
# 个人笔记
kb_discover("TODO", vault_id="personal")

# 团队知识
kb_discover("开发规范", vault_id="team")

# 公司知识库
kb_discover("员工手册", vault_id="company")
```

## 最佳实践

### 1. 合理划分知识库

**按相关性划分**：
- ✅ 好：按领域、项目、用途划分
- ❌ 差：按文件大小、创建时间划分

**控制数量**：
- ✅ 建议：3-10 个知识库
- ❌ 过多：影响搜索效率
- ❌ 过少：失去分类意义

### 2. 统一命名规范

**vault_id 命名**：
- ✅ 使用有意义的名称
- ✅ 保持简短（10 字符以内）
- ✅ 使用一致的命名风格
- ❌ 避免过长或复杂的名称

**示例**：
```
✅ medical, tech, legal
✅ proj_a, proj_b, shared
❌ my-medical-knowledge-base-2024
❌ temp, test, backup
```

### 3. 设计搜索策略

**明确领域时**：
```python
# 指定库搜索，更快更准确
kb_discover("关键词", vault_id="specific_vault")
```

**不确定时**：
```python
# 跨库搜索，覆盖面广
kb_discover("关键词")  # 搜索所有库
```

**分步搜索**：
```python
# 1. 先在主库搜索
results = kb_discover("关键词", vault_id="primary")

# 2. 如果没找到，扩大范围
if not results:
    results = kb_discover("关键词")  # 全库搜索
```

### 4. 维护知识库

**定期更新**：
- 重新上传更新的 zip 文件导入
- 或使用 `/kb rebuild` 从现有 files/ 重建索引
- 检查 `/kb status` 确认状态

**清理无用库**：
- 从配置中移除
- 删除对应的数据目录
- 释放存储空间

## 高级用法

### 动态库选择

根据用户查询动态选择知识库：

```python
def choose_vault(query):
    # 根据关键词判断领域
    if any(word in query for word in ["疾病", "治疗", "药物"]):
        return "medical"
    elif any(word in query for word in ["代码", "API", "函数"]):
        return "tech"
    elif any(word in query for word in ["合同", "法规", "诉讼"]):
        return "legal"
    else:
        return None  # 跨库搜索

query = "川崎病治疗方案"
vault = choose_vault(query)
results = kb_discover(query, vault_id=vault)
```

### 多库并行搜索

同时搜索多个相关库：

```python
def multi_vault_search(query, vaults):
    all_results = []
    for vault in vaults:
        results = kb_discover(query, vault_id=vault, limit=5)
        all_results.extend(results)
    
    # 按 score 重新排序
    all_results.sort(key=lambda x: x["score"], reverse=True)
    return all_results[:10]

# 搜索医学相关的多个库
results = multi_vault_search(
    "治疗方案",
    ["medical", "clinical_trials", "drug_database"]
)
```

### 库间比对

比较不同库中的相关内容：

```python
def compare_across_vaults(query, vaults):
    comparison = {}
    for vault in vaults:
        results = kb_discover(query, vault_id=vault, limit=3)
        comparison[vault] = results
    return comparison

# 比较不同来源的信息
comparison = compare_across_vaults(
    "async programming",
    ["python_docs", "javascript_docs", "rust_docs"]
)

for vault, results in comparison.items():
    print(f"{vault}: {len(results)} results")
```

## 故障排除

### 问题：找不到指定的知识库

**现象**：
```
vault 'xxx' not found
```

**原因**：
- vault_id 拼写错误
- 知识库未配置
- 知识库未导入

**解决**：
1. 检查配置中的 vault id
2. 使用 `/kb status` 查看已有库
3. 确认 vault_id 大小写匹配

### 问题：跨库搜索返回空

**原因**：
- 所有库都没有匹配内容
- 查询词太具体

**解决**：
1. 使用更通用的查询词
2. 分别搜索各个库检查
3. 确认库已正确导入

### 问题：引用格式不生效

**现象**：
```bash
/kb read medical:note.md
# 提示找不到笔记
```

**原因**：
- 冒号前后有空格
- vault_id 错误
- 路径不存在

**解决**：
```bash
# 错误
/kb read medical : note.md

# 正确
/kb read medical:note.md
```

### 问题：搜索结果编号失效

**原因**：
- 新会话中使用了旧编号
- 搜索结果已被新搜索覆盖

**解决**：
- 重新搜索获取编号
- 或直接使用 vault_id:path 格式

## 性能考虑

### 库数量影响

**搜索性能**：
- 3-5 个库：影响很小
- 6-10 个库：轻微影响
- 10+ 个库：建议指定 vault_id

**建议**：
- 常用查询：指定 vault_id
- 探索性查询：跨库搜索

### 库大小影响

**单库建议大小**：
- 小型：< 100 篇笔记
- 中型：100-1000 篇
- 大型：1000-5000 篇
- 超大：> 5000 篇（考虑拆分）

**优化建议**：
- 大库优先使用 outline 模式
- 合理配置 max_read_chars
- 善用 section 模式精确读取

## 迁移和备份

### 导出知识库

```bash
# 手动压缩 files 目录
cd /data/vaults/medical/files
zip -r /backup/medical_$(date +%Y%m%d).zip .
```

### 导入已有知识库

```json
{
  "vaults": [
    {
      "id": "medical",
      "path": "/backup/medical_20240101.zip"
    }
  ]
}
```

### 迁移到新环境

**方案 1：从 zip 迁移**
1. 复制配置文件
2. 复制 zip 文件
3. 配置数据目录
4. 重新上传 zip 导入

**方案 2：从 files/ 迁移**
1. 复制整个 data_dir/vaults 目录
2. 配置数据目录指向复制的位置
3. 执行 `/kb rebuild` 重建索引

### 数据备份

**建议备份内容**：
- 原始 zip 文件（首次导入时）
- data_dir/vaults 目录（包含所有 files/ 和索引）
- 配置文件

**可选备份**：
- 索引数据库（可从 files/ 重建）

**不需要备份**：
- 临时导入目录
