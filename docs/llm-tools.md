# LLM 工具接口

本文档详细说明 NoteSift 提供的 LLM 工具接口。

## 工具概览

NoteSift 提供两个主要的 LLM 工具：
- `kb_discover` - 搜索发现候选笔记
- `kb_read` - 读取笔记内容

## kb_discover

在知识库中搜索候选笔记，返回元数据和必要的短片段。

### 函数签名

```python
kb_discover(
    query: str,           # 搜索关键词或正则表达式
    limit: int = 5,       # 返回候选数量（1-10）
    regex: bool = False,  # 是否使用正则表达式搜索
    vault_id: str = ""    # 指定知识库ID，留空则跨库搜索
)
```

### 参数说明

**query**（字符串，必填）
- 搜索关键词或正则表达式
- 多词查询：所有词都必须存在
- 示例：`"川崎病 IVIG"` 要求两个词都匹配

**limit**（整数，可选）
- 返回候选数量
- 默认值：5
- 取值范围：1-10（自动限制）

**regex**（布尔值，可选）
- 是否使用正则表达式搜索
- 默认值：false
- 正则语法：Python re 模块语法

**vault_id**（字符串，可选）
- 指定知识库 ID
- 留空：跨所有知识库搜索
- 指定：仅在该库中搜索

### 返回格式

```json
{
  "results": [
    {
      "note_id": "abc123",
      "vault_id": "medical",
      "path": "cardiology/kawasaki.md",
      "title": "川崎病",
      "tags": ["儿科学", "心血管"],
      "aliases": ["KD", "Kawasaki Disease"],
      "score": 180,
      "matched_fields": ["title", "tags"],
      "snippets": ["正文命中片段（仅命中正文时返回）"],
      "source_ref": "cardiology/kawasaki.md#川崎病"
    }
  ]
}
```

### 字段说明

- `note_id` - 笔记唯一标识符，用于后续读取
- `vault_id` - 来源知识库 ID
- `path` - 笔记在知识库中的路径
- `title` - 笔记标题
- `tags` - 标签列表
- `aliases` - 别名列表
- `score` - 匹配分数（越高越相关）
- `matched_fields` - 命中的字段列表
- `snippets` - 正文片段（仅命中正文时返回）
- `source_ref` - 引用格式（路径#标题）

### 使用示例

**基础搜索**：
```python
# 在默认库搜索
kb_discover("川崎病治疗")

# 跨所有库搜索
kb_discover("async programming", limit=10)
```

**指定库搜索**：
```python
# 在医学库搜索
kb_discover("IVIG治疗", vault_id="medical")

# 在技术库搜索
kb_discover("Python async", vault_id="tech")
```

**正则表达式搜索**：
```python
# 搜索函数定义
kb_discover(r"def\s+\w+", regex=True, vault_id="tech")

# 搜索剂量相关
kb_discover(r"\d+\s*mg", regex=True, vault_id="medical")
```

### 匹配规则

**字段权重**（按优先级排序）：
1. 标题（title）- 权重 100
2. 别名（aliases）- 权重 80
3. 标签（tags）- 权重 70
4. 路径（path）- 权重 60
5. 标题层级（headings）- 权重 50
6. 正文（body）- 权重 10

**分数计算**：
- 命中字段的权重之和
- 命中多个字段得分更高
- 用于结果排序

**片段返回条件**：
- 仅命中正文时返回片段
- 或命中正文 + 没有命中元数据字段时返回

### 最佳实践

**1. 优先使用 kb_discover**
```python
# 好的流程
results = kb_discover("川崎病")
if results:
    content = kb_read(results[0]["note_id"], mode="outline")
```

**2. 控制返回数量**
```python
# 快速查询：返回少量结果
kb_discover("keyword", limit=3)

# 全面查询：返回更多结果
kb_discover("keyword", limit=10)
```

**3. 善用 vault_id**
```python
# 明确领域时指定库
kb_discover("疾病", vault_id="medical")

# 不确定时跨库搜索
kb_discover("keyword")  # 搜索所有库
```

**4. 评估搜索结果**
```python
results = kb_discover("query", limit=5)
# 检查 score 和 matched_fields 选择最相关的
relevant = [r for r in results if r["score"] > 100]
```

## kb_read

读取知识库中的具体笔记内容。

### 函数签名

```python
kb_read(
    note_ref: str,           # note_id、path 或 vault_id:note_id
    mode: str = "outline",   # 读取模式
    heading: str = "",       # section 模式下的标题关键词
    query: str = "",         # snippets 模式下的检索词
    page: int = 1,           # paged 模式下的页码
    vault_id: str = ""       # 指定知识库ID
)
```

### 参数说明

**note_ref**（字符串，必填）
- note_id：笔记唯一标识符
- path：笔记路径
- vault_id:note_id：跨库引用格式

**mode**（字符串，可选）
- `"outline"` - 元数据 + 标题树（默认）
- `"summary"` - 摘要标注块
- `"section"` - 指定章节
- `"snippets"` - 查询片段
- `"full"` - 完整正文

**heading**（字符串，可选）
- 仅在 `mode="section"` 时使用
- 章节标题的关键词
- 不区分大小写匹配

**query**（字符串，可选）
- 仅在 `mode="snippets"` 时使用
- 检索词，用于提取相关片段

**page**（整数，可选）
- 仅在 paged 策略 + `mode="full"` 时使用
- 页码，从 1 开始
- 默认值：1

**vault_id**（字符串，可选）
- 指定知识库 ID
- 如果 note_ref 包含 `:`，则从 note_ref 解析
- 否则使用此参数
- 都没有则使用 `"default"`

### 返回格式

```json
{
  "found": true,
  "note_id": "abc123",
  "path": "cardiology/kawasaki.md",
  "title": "川崎病",
  "tags": ["儿科学", "心血管"],
  "aliases": ["KD"],
  "headings": [
    {
      "title": "川崎病",
      "level": 1,
      "line_start": 1,
      "line_end": 50
    }
  ],
  "source_ref": "cardiology/kawasaki.md#川崎病",
  "truncated": false,
  "content": "笔记内容...",
  "next_action_hint": "",
  "page_info": {
    "current": 1,
    "total": 3,
    "has_next": true,
    "has_prev": false
  }
}
```

### 字段说明

**基础字段**：
- `found` - 是否找到笔记
- `note_id` - 笔记 ID
- `path` - 笔记路径
- `title` - 笔记标题
- `tags` - 标签列表
- `aliases` - 别名列表
- `headings` - 标题树
- `source_ref` - 引用格式

**内容字段**：
- `content` - 笔记内容（根据 mode 不同）
- `truncated` - 是否被截断
- `next_action_hint` - 下一步建议（被截断时）

**分页字段**（paged 模式）：
- `page_info.current` - 当前页码
- `page_info.total` - 总页数
- `page_info.has_next` - 是否有下一页
- `page_info.has_prev` - 是否有上一页

### 使用示例

**基础读取**：
```python
# 读取大纲
kb_read("abc123", mode="outline")

# 读取完整内容
kb_read("abc123", mode="full")
```

**跨库读取**：
```python
# 方式 1：使用 vault_id 参数
kb_read("note.md", vault_id="medical")

# 方式 2：使用前缀格式
kb_read("medical:note.md")
```

**章节读取**：
```python
# 读取治疗章节
kb_read("abc123", mode="section", heading="治疗")

# 读取 IVIG 章节
kb_read("abc123", mode="section", heading="IVIG")
```

**片段读取**：
```python
# 查找关键词
kb_read("abc123", mode="snippets", query="IVIG")

# 查找代码片段
kb_read("abc123", mode="snippets", query="async def")
```

**分页读取**：
```python
# 读取第 1 页
result = kb_read("abc123", mode="full", page=1)

# 检查是否有下一页
if result.get("page_info", {}).get("has_next"):
    next_page = kb_read("abc123", mode="full", page=2)
```

### 最佳实践

**1. 渐进式读取**
```python
# 第一步：了解结构
outline = kb_read(note_id, mode="outline")

# 第二步：查看要点
summary = kb_read(note_id, mode="summary")

# 第三步：读取感兴趣的章节
content = kb_read(note_id, mode="section", heading="重点章节")
```

**2. 处理长内容**
```python
# 方式 1：使用 compressed 策略（配置中设置）
preview = kb_read(note_id, mode="full")
# 返回结构化骨架

# 方式 2：使用 paged 策略（配置中设置）
page1 = kb_read(note_id, mode="full", page=1)
if page1.get("page_info", {}).get("has_next"):
    page2 = kb_read(note_id, mode="full", page=2)

# 方式 3：直接读取需要的章节
section = kb_read(note_id, mode="section", heading="目标章节")
```

**3. 错误处理**
```python
result = kb_read(note_id, mode="full")

if not result.get("found"):
    # 笔记不存在
    error = result.get("error", "unknown error")
    
if result.get("truncated"):
    # 内容被截断
    hint = result.get("next_action_hint")
    # 按提示使用其他模式
```

**4. 引用格式**
```python
# 在结果中包含 source_ref
result = kb_read(note_id, mode="full")
source = result.get("source_ref")
# 格式：path#title
# 可用于回答时注明来源
```

## 工作流示例

### 场景 1：简单查询

```python
# 1. 搜索
results = kb_discover("川崎病治疗", limit=5)

# 2. 选择最相关的
best = results[0]

# 3. 读取大纲
outline = kb_read(best["note_id"], mode="outline")

# 4. 读取详细内容
content = kb_read(best["note_id"], mode="full")
```

### 场景 2：精确定位

```python
# 1. 搜索笔记
results = kb_discover("Python async", vault_id="tech")

# 2. 在笔记中查找具体内容
for result in results:
    snippets = kb_read(
        result["note_id"],
        mode="snippets",
        query="event loop"
    )
    if "event loop" in snippets.get("content", ""):
        # 找到相关内容
        break

# 3. 读取该章节
section = kb_read(
    result["note_id"],
    mode="section",
    heading="event loop"
)
```

### 场景 3：多源综合

```python
# 1. 跨库搜索
results = kb_discover("treatment guidelines", limit=10)

# 2. 按来源分组
by_vault = {}
for r in results:
    vault = r["vault_id"]
    if vault not in by_vault:
        by_vault[vault] = []
    by_vault[vault].append(r)

# 3. 从各库读取相关内容
summaries = []
for vault, notes in by_vault.items():
    for note in notes[:2]:  # 每库取前两条
        content = kb_read(
            note["note_id"],
            mode="summary",
            vault_id=vault
        )
        summaries.append({
            "vault": vault,
            "title": note["title"],
            "content": content
        })
```

### 场景 4：长文档处理

```python
# 1. 搜索长文档
results = kb_discover("comprehensive guide", limit=3)
note_id = results[0]["note_id"]

# 2. 获取结构（compressed 策略）
preview = kb_read(note_id, mode="full")
# 返回所有标题 + 各节预览

# 3. 根据预览选择章节
sections_to_read = ["introduction", "advanced topics"]

# 4. 逐节详细阅读
contents = []
for heading in sections_to_read:
    section = kb_read(note_id, mode="section", heading=heading)
    contents.append(section)
```

## 性能优化

### 1. 控制调用次数

```python
# 不好：过多调用
for result in kb_discover("query", limit=20):
    kb_read(result["note_id"], mode="full")  # 20 次调用

# 好：有选择地读取
results = kb_discover("query", limit=20)
top_results = results[:3]  # 只读前 3 条
for result in top_results:
    kb_read(result["note_id"], mode="outline")  # 轻量级读取
```

### 2. 使用轻量级模式

```python
# 不好：直接使用 full
kb_read(note_id, mode="full")

# 好：先用 outline
outline = kb_read(note_id, mode="outline")
# 根据需要再深入
if need_detail:
    content = kb_read(note_id, mode="section", heading="target")
```

### 3. 缓存结果

```python
# 缓存搜索结果
search_cache = {}

def cached_discover(query):
    if query not in search_cache:
        search_cache[query] = kb_discover(query)
    return search_cache[query]

# 缓存已读笔记
read_cache = {}

def cached_read(note_id, mode="outline"):
    key = f"{note_id}:{mode}"
    if key not in read_cache:
        read_cache[key] = kb_read(note_id, mode=mode)
    return read_cache[key]
```

## 常见问题

### Q: kb_discover 返回空结果？

**原因**：
- 查询词不存在
- vault_id 错误
- 知识库未导入

**解决**：
- 使用更通用的查询词
- 检查 vault_id
- 使用跨库搜索（不指定 vault_id）

### Q: kb_read 返回 found=false？

**原因**：
- note_id 错误
- vault_id 错误
- 笔记已删除

**解决**：
- 确认 note_id 正确
- 检查 vault_id
- 重新搜索获取最新 note_id

### Q: 如何知道使用哪个 mode？

**建议顺序**：
1. `outline` - 先了解结构
2. `summary` - 查看要点
3. `section` - 读取感兴趣的部分
4. `full` - 需要时读取完整内容

### Q: paged 模式如何判断结束？

**检查 page_info**：
```python
result = kb_read(note_id, mode="full", page=1)
if not result.get("page_info", {}).get("has_next"):
    # 已是最后一页
```

### Q: 正则搜索不生效？

**检查项**：
- 正则语法是否正确
- `regex=True` 是否设置
- 是否需要转义特殊字符

**示例**：
```python
# 错误
kb_discover("def function()", regex=True)  # () 未转义

# 正确
kb_discover(r"def\s+function\(\)", regex=True)
```
