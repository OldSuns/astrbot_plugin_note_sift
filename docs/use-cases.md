# 使用场景

本文档提供 NoteSift 的常见使用场景和最佳实践。

## 场景 1：医学知识查询

### 配置

```json
{
  "vaults": [
    {"id": "medical", "path": "/data/medical_knowledge.zip"}
  ],
  "full_over_limit_strategy": "paged",
  "max_read_chars": 8000
}
```

### 工作流

**1. 疾病查询**

```bash
# 命令行
/kb search medical:川崎病
/kb read 1 outline

# LLM 工具
results = kb_discover("川崎病", vault_id="medical")
outline = kb_read(results[0]["note_id"], mode="outline")
```

**2. 治疗方案查询**

```python
# 搜索疾病
results = kb_discover("川崎病", vault_id="medical")
note_id = results[0]["note_id"]

# 读取治疗章节
treatment = kb_read(note_id, mode="section", heading="治疗")
```

**3. 药物信息查询**

```python
# 在所有医学笔记中搜索药物
results = kb_discover("IVIG", vault_id="medical", limit=5)

# 提取相关片段
for result in results:
    snippets = kb_read(
        result["note_id"],
        mode="snippets",
        query="IVIG剂量"
    )
```

### 提示

- 使用 section 模式精确读取治疗、诊断等章节
- 善用 snippets 模式快速定位药物剂量信息
- 标签可用于分类（如：儿科学、心血管）

## 场景 2：技术文档浏览

### 配置

```json
{
  "vaults": [
    {"id": "python", "path": "/docs/python_docs.zip"},
    {"id": "javascript", "path": "/docs/js_docs.zip"},
    {"id": "devops", "path": "/docs/devops.zip"}
  ],
  "full_over_limit_strategy": "compressed",
  "compressed_section_preview_chars": 200
}
```

### 工作流

**1. API 文档查询**

```python
# 跨语言搜索
results = kb_discover("async programming", limit=10)

# 按语言分组
by_language = {}
for r in results:
    lang = r["vault_id"]
    if lang not in by_language:
        by_language[lang] = []
    by_language[lang].append(r)

# 对比各语言实现
for lang, notes in by_language.items():
    print(f"\n{lang}:")
    for note in notes:
        content = kb_read(note["note_id"], mode="summary")
```

**2. 代码示例查找**

```python
# 搜索代码片段
results = kb_discover("async def", regex=True, vault_id="python")

# 读取完整示例
for result in results:
    code = kb_read(
        result["note_id"],
        mode="snippets",
        query="async def"
    )
```

**3. 长教程阅读**

```python
# 使用 compressed 模式预览
preview = kb_read("python:tutorial.md", mode="full")
# 返回结构 + 各节预览

# 选择感兴趣的章节深入阅读
chapter = kb_read(
    "python:tutorial.md",
    mode="section",
    heading="Advanced Topics"
)
```

### 提示

- compressed 模式适合快速预览技术文档
- 使用正则搜索定位代码模式
- 善用 outline 了解文档结构

## 场景 3：团队知识库

### 配置

```json
{
  "vaults": [
    {"id": "engineering", "path": "/team/engineering.zip"},
    {"id": "product", "path": "/team/product.zip"},
    {"id": "business", "path": "/team/business.zip"}
  ],
  "enable_acl": true,
  "allowed_sessions": "team_member_1\nteam_member_2\nteam_member_3"
}
```

### 工作流

**1. 开发规范查询**

```bash
/kb search engineering:代码规范
/kb read 1 full
```

**2. 产品需求文档**

```python
# 搜索需求文档
results = kb_discover("用户认证需求", vault_id="product")

# 读取详细需求
for result in results:
    doc = kb_read(result["note_id"], mode="full")
```

**3. 跨部门信息查找**

```python
# 搜索所有部门的相关信息
results = kb_discover("API接口规范")

# 按部门整理
by_dept = {}
for r in results:
    dept = r["vault_id"]
    if dept not in by_dept:
        by_dept[dept] = []
    by_dept[dept].append(r)
```

### 提示

- 使用 ACL 控制访问权限
- 按部门或功能划分知识库
- 定期更新和维护

## 场景 4：个人笔记管理

### 配置

```json
{
  "vaults": [
    {"path": "/home/user/notes.zip"}
  ],
  "full_over_limit_strategy": "paged",
  "default_read_mode": "outline"
}
```

### 工作流

**1. 快速记录查找**

```bash
/kb search TODO
/kb read 1
```

**2. 主题笔记整理**

```python
# 搜索特定主题
results = kb_discover("Python学习笔记", limit=10)

# 按标签分组
by_tag = {}
for r in results:
    for tag in r["tags"]:
        if tag not in by_tag:
            by_tag[tag] = []
        by_tag[tag].append(r)
```

**3. 长期笔记回顾**

```python
# 搜索旧笔记
results = kb_discover("2024")

# 快速浏览
for result in results:
    summary = kb_read(result["note_id"], mode="summary")
```

### 提示

- 合理使用标签组织笔记
- 使用别名方便搜索
- 定期整理和归档

## 场景 5：教育和学习

### 配置

```json
{
  "vaults": [
    {"id": "math", "path": "/courses/math.zip"},
    {"id": "physics", "path": "/courses/physics.zip"},
    {"id": "chemistry", "path": "/courses/chemistry.zip"}
  ],
  "full_over_limit_strategy": "paged",
  "max_read_chars": 6000
}
```

### 工作流

**1. 知识点学习**

```python
# 搜索知识点
results = kb_discover("微积分基本定理", vault_id="math")

# 先看大纲
outline = kb_read(results[0]["note_id"], mode="outline")

# 逐节学习
sections = outline["headings"]
for section in sections:
    content = kb_read(
        results[0]["note_id"],
        mode="section",
        heading=section["title"]
    )
```

**2. 习题查找**

```python
# 搜索习题
results = kb_discover("习题", vault_id="math")

# 提取习题部分
for result in results:
    exercises = kb_read(
        result["note_id"],
        mode="section",
        heading="习题"
    )
```

**3. 跨学科关联**

```python
# 搜索相关概念
math_results = kb_discover("能量", vault_id="math")
physics_results = kb_discover("能量", vault_id="physics")

# 对比不同学科的定义
```

### 提示

- 按学科划分知识库
- 使用标题层级组织知识点
- 善用搜索功能复习

## 场景 6：研究和写作

### 配置

```json
{
  "vaults": [
    {"id": "literature", "path": "/research/literature.zip"},
    {"id": "notes", "path": "/research/notes.zip"},
    {"id": "drafts", "path": "/research/drafts.zip"}
  ],
  "full_over_limit_strategy": "compressed"
}
```

### 工作流

**1. 文献引用查找**

```python
# 搜索相关文献
results = kb_discover("机器学习综述", vault_id="literature")

# 提取引用信息
for result in results:
    citation = kb_read(result["note_id"], mode="summary")
```

**2. 研究笔记整理**

```python
# 搜索笔记
notes = kb_discover("实验结果", vault_id="notes")

# 按主题整理
themes = {}
for note in notes:
    tags = note["tags"]
    for tag in tags:
        if tag not in themes:
            themes[tag] = []
        themes[tag].append(note)
```

**3. 草稿管理**

```python
# 查看所有草稿
drafts = kb_discover("", vault_id="drafts")

# 使用 compressed 模式快速预览
for draft in drafts:
    preview = kb_read(draft["note_id"], mode="full")
    # 查看结构和要点
```

### 提示

- 文献、笔记、草稿分库管理
- 使用标签关联相关内容
- compressed 模式快速预览草稿

## 场景 7：客户支持知识库

### 配置

```json
{
  "vaults": [
    {"id": "faq", "path": "/support/faq.zip"},
    {"id": "troubleshooting", "path": "/support/troubleshooting.zip"},
    {"id": "tutorials", "path": "/support/tutorials.zip"}
  ],
  "enable_acl": true,
  "allowed_sessions": "support_agent_1\nsupport_agent_2"
}
```

### 工作流

**1. 快速问题解答**

```python
# 搜索常见问题
results = kb_discover("如何重置密码", vault_id="faq")

# 获取答案
answer = kb_read(results[0]["note_id"], mode="full")
```

**2. 故障排查**

```python
# 搜索故障症状
results = kb_discover("登录失败", vault_id="troubleshooting")

# 读取排查步骤
for result in results:
    steps = kb_read(
        result["note_id"],
        mode="section",
        heading="解决步骤"
    )
```

**3. 教程推荐**

```python
# 根据用户问题推荐教程
user_question = "如何使用高级功能"
tutorials = kb_discover(user_question, vault_id="tutorials")

# 返回教程大纲
for tutorial in tutorials:
    outline = kb_read(tutorial["note_id"], mode="outline")
```

### 提示

- FAQ、故障排查、教程分库
- 使用标题和标签便于检索
- ACL 控制内部使用

## 场景 8：法律文档管理

### 配置

```json
{
  "vaults": [
    {"id": "contracts", "path": "/legal/contracts.zip"},
    {"id": "regulations", "path": "/legal/regulations.zip"},
    {"id": "cases", "path": "/legal/cases.zip"}
  ],
  "full_over_limit_strategy": "paged",
  "max_read_chars": 10000
}
```

### 工作流

**1. 合同条款查询**

```python
# 搜索特定条款
results = kb_discover("保密条款", vault_id="contracts")

# 读取完整条款
clause = kb_read(
    results[0]["note_id"],
    mode="section",
    heading="保密"
)
```

**2. 法规查阅**

```python
# 搜索相关法规
regs = kb_discover("数据保护", vault_id="regulations")

# 分页阅读
for page in range(1, 4):
    content = kb_read(
        regs[0]["note_id"],
        mode="full",
        page=page
    )
```

**3. 案例检索**

```python
# 搜索相似案例
cases = kb_discover("违约责任", vault_id="cases")

# 提取关键信息
for case in cases:
    summary = kb_read(case["note_id"], mode="summary")
```

### 提示

- 按文档类型分库
- 使用 paged 模式阅读长文档
- 善用 section 模式定位条款

## 最佳实践总结

### 1. 知识库组织

**按用途分类**：
- ✅ 医学、技术、法律等专业领域
- ✅ 个人、团队、公司等使用范围
- ✅ 文献、笔记、草稿等内容类型

**控制规模**：
- 单库建议 < 5000 篇笔记
- 总库数建议 3-10 个
- 超大库考虑拆分

### 2. 搜索策略

**渐进式搜索**：
1. 先用通用关键词搜索
2. 根据结果调整查询
3. 必要时使用正则表达式

**指定范围**：
- 明确领域时指定 vault_id
- 探索性查询跨库搜索
- 善用标签和路径

### 3. 读取策略

**渐进式阅读**：
1. outline - 了解结构
2. summary - 查看要点
3. section - 读取关键部分
4. full - 详细阅读（必要时）

**选择模式**：
- 短内容：full
- 长内容：paged 或 compressed
- 定位内容：section 或 snippets

### 4. 性能优化

**减少调用**：
- 一次搜索，多次利用结果
- 缓存常用查询结果
- 避免重复读取

**合理配置**：
- 根据 LLM 窗口设置 max_read_chars
- 按需要选择读取策略
- 控制 limit 参数

### 5. 维护管理

**定期更新**：
- 更新过期内容
- 添加新增笔记
- 重建索引

**备份策略**：
- 保留原始 zip 文件
- 定期备份配置
- 导出重要内容

### 6. 安全考虑

**访问控制**：
- 敏感内容启用 ACL
- 定期审查白名单
- 记录访问日志

**数据保护**：
- 不在笔记中存储密码
- 脱敏敏感信息
- 加密重要文件

## 进阶技巧

### 1. 动态库选择

根据查询内容自动选择知识库：

```python
def smart_search(query):
    # 领域判断
    if "疾病" in query or "治疗" in query:
        vault = "medical"
    elif "代码" in query or "API" in query:
        vault = "tech"
    elif "条款" in query or "法规" in query:
        vault = "legal"
    else:
        vault = None  # 跨库
    
    return kb_discover(query, vault_id=vault)
```

### 2. 多轮对话

利用上下文优化查询：

```python
# 第一轮：搜索
results = kb_discover("川崎病")

# 第二轮：根据用户反馈细化
if user_wants_treatment:
    details = kb_read(
        results[0]["note_id"],
        mode="section",
        heading="治疗"
    )
```

### 3. 结果聚合

整合多个来源的信息：

```python
def aggregate_info(query):
    # 从多个库搜索
    all_results = []
    for vault in ["medical", "research", "clinical"]:
        results = kb_discover(query, vault_id=vault, limit=3)
        all_results.extend(results)
    
    # 去重和排序
    unique = {}
    for r in all_results:
        if r["title"] not in unique:
            unique[r["title"]] = r
    
    return sorted(unique.values(), key=lambda x: x["score"], reverse=True)
```
