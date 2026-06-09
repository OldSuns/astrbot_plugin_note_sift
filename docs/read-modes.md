# 读取模式

本文档详细说明 NoteSift 的各种读取模式及其使用场景。

## 模式概览

| 模式 | 返回内容 | 适用场景 |
|------|---------|---------|
| `outline` | 元数据 + 标题树 | 快速了解笔记结构 |
| `summary` | 标注块（callout） | 查看笔记要点 |
| `section` | 指定章节内容 | 精确读取某个章节 |
| `snippets` | 查询相关片段 | 在笔记中查找特定内容 |
| `full` | 完整正文 | 详细阅读完整内容 |

## outline（大纲模式）

### 返回内容

- 笔记标题
- 文件路径
- 标签（tags）
- 别名（aliases）
- 完整的标题层级树

### 返回示例

```
# 川崎病
cardiology/kawasaki.md
tags: 儿科学, 心血管
aliases: KD, Kawasaki Disease

Headings:
- 川崎病
  - 概述
  - 病因
  - 临床表现
    - 主要症状
    - 次要症状
  - 诊断标准
  - 治疗方案
    - IVIG 治疗
    - 阿司匹林治疗
  - 预后
```

### 使用场景

✅ **推荐场景**：
- 首次查看笔记，了解整体结构
- 决定后续读取哪个章节
- 快速浏览笔记主题
- 检查笔记组织结构

❌ **不适用场景**：
- 需要查看具体内容
- 需要详细信息

### 命令示例

```bash
# 命令行
/kb read 1 outline

# LLM 工具
kb_read("kawasaki.md", mode="outline")
```

## summary（摘要模式）

### 返回内容

提取笔记中的 Obsidian 标注块（callout）：
- `> [!summary]` - 摘要
- `> [!warning]` - 警告
- `> [!tip]` - 提示

### 返回示例

```
# 川崎病
cardiology/kawasaki.md

> [!summary] 概述
> 川崎病是一种急性全身性血管炎，主要影响中小动脉。
> 好发于 5 岁以下儿童，尤其是 6 个月至 2 岁。

> [!warning] 重要提示
> 及时诊断和治疗至关重要，可减少冠状动脉瘤的发生率。

> [!tip] 诊断要点
> 持续发热 5 天以上 + 4 项主要症状即可诊断。
```

### 使用场景

✅ **推荐场景**：
- 快速获取笔记要点
- 查看关键提示和警告
- 获取作者标注的重点

❌ **不适用场景**：
- 笔记中没有标注块
- 需要完整内容
- 需要详细论述

### 命令示例

```bash
# 命令行
/kb read 1 summary

# LLM 工具
kb_read("kawasaki.md", mode="summary")
```

### 注意事项

- 如果笔记中没有标注块，返回内容为空
- 仅识别上述三种标注类型
- 保留原始 Markdown 格式

## section（章节模式）

### 返回内容

指定标题下的完整章节内容，包含：
- 章节标题
- 章节正文
- 子章节内容

### 参数

- `heading`（必填）：章节标题的关键词

### 返回示例

```
## 治疗方案

川崎病的治疗主要包括：

### IVIG 治疗

静脉注射免疫球蛋白（IVIG）是川崎病的首选治疗方法...

### 阿司匹林治疗

阿司匹林在川崎病治疗中有两个作用...
```

### 使用场景

✅ **推荐场景**：
- 已知要读取的章节
- 笔记太长，只需其中一部分
- 精确定位特定主题

❌ **不适用场景**：
- 不确定章节名称
- 需要多个章节
- 章节内容仍然太长

### 命令示例

```bash
# LLM 工具（命令行不直接支持 heading 参数）
kb_read("kawasaki.md", mode="section", heading="治疗")
kb_read("kawasaki.md", mode="section", heading="IVIG")
```

### 匹配规则

- 关键词匹配（不区分大小写）
- 如果多个标题包含关键词，返回第一个
- 如果没有匹配，返回第一个章节

### 注意事项

- 返回从标题开始到下一个同级标题之前的内容
- 包含所有子章节
- 仍受 `max_read_chars` 限制

## snippets（片段模式）

### 返回内容

包含查询词的相关正文片段。

### 参数

- `query`（必填）：检索词

### 返回示例

```
# 川崎病
cardiology/kawasaki.md

...静脉注射免疫球蛋白（IVIG）是川崎病的首选治疗方法。
通常剂量为 2g/kg，单次输注...

...研究表明，早期使用 IVIG 治疗可以显著降低冠状动脉瘤
的发生率，从 25% 降至 5% 以下...
```

### 使用场景

✅ **推荐场景**：
- 在长笔记中查找特定内容
- 快速定位关键信息
- 获取查询词的上下文

❌ **不适用场景**：
- 需要完整章节
- 需要连贯阅读
- 查询词出现次数太多

### 命令示例

```bash
# LLM 工具
kb_read("kawasaki.md", mode="snippets", query="IVIG")
kb_read("python.md", mode="snippets", query="async")
```

### 片段生成规则

- 以查询词位置为中心
- 前后各扩展一定字符
- 受 `max_read_chars` 限制

## full（完整模式）

### 行为说明

根据 `full_over_limit_strategy` 配置返回不同结果：

#### strict 策略

**内容未超限**：返回完整正文

**内容超限**：
```
# 川崎病
cardiology/kawasaki.md
内容超过单次读取上限。可按 heading 使用 section 模式继续读取。

Headings:
- 川崎病
  - 概述
  - 病因
  ...
```

#### paged 策略

**返回内容**：
- 当前页内容（在段落边界分页）
- 分页信息

**分页信息**：
```json
{
  "current": 2,
  "total": 5,
  "has_next": true,
  "has_prev": true
}
```

**返回示例**：
```
# Python 异步编程
python/async.md
页 2/5
提示: 使用 page 参数读取下一页

## 事件循环

事件循环是异步编程的核心...

（第二页内容）
```

#### compressed 策略

**返回内容**：
- 所有标题
- 每个章节的开头预览（N 字符）

**返回示例**：
```
# Python 异步编程

Python 3.5+ 引入了 async/await 语法，使异步编程更加直观...

## 基础概念

异步编程允许程序在等待 I/O 操作时执行其他任务。主要概念包括：
- 协程（Coroutine）
- 事件循环（Event Loop）
- Future 和 Task

## async/await 语法

async 关键字用于定义协程函数，await 用于等待异步操作完成...

（每节仅显示前 N 字符）
```

### 使用场景

| 策略 | 推荐场景 | 不推荐场景 |
|------|---------|-----------|
| strict | 强制用户精确读取 | 需要完整浏览 |
| paged | 完整阅读长文档 | 仅需预览 |
| compressed | 快速预览结构和内容 | 需要详细内容 |

### 命令示例

```bash
# strict 模式（默认）
/kb read 1 full

# paged 模式
/kb read 1 full 1    # 第 1 页
/kb read 1 full 2    # 第 2 页

# LLM 工具
kb_read("note.md", mode="full", page=1)
kb_read("note.md", mode="full", page=2)
```

### 注意事项

**strict 策略**：
- 短内容直接返回
- 长内容拒绝，引导使用其他模式

**paged 策略**：
- 分页边界在 `\n\n`（段落间）
- 不会截断段落
- 页大小 = `max_read_chars`

**compressed 策略**：
- 预览长度可配置（`compressed_section_preview_chars`）
- 保留完整结构
- 牺牲内容完整性

## 模式选择建议

### 决策流程

```
开始
 ↓
知道要什么内容？
 ├─ 否 → 使用 outline 查看结构
 └─ 是
     ↓
     需要完整内容？
     ├─ 否 → 知道章节？
     │       ├─ 是 → 使用 section
     │       └─ 否 → 使用 snippets
     └─ 是
         ↓
         内容长度？
         ├─ 短 → 使用 full
         └─ 长 → 选择策略
                 ├─ 需要详细阅读 → paged
                 ├─ 仅需预览 → compressed
                 └─ 明确章节 → section
```

### 常见组合

**探索式阅读**：
1. `outline` - 了解结构
2. `summary` - 查看要点
3. `section` - 读取感兴趣的章节

**查找式阅读**：
1. `snippets` - 定位关键词
2. `section` - 读取相关章节

**完整式阅读**：
1. `outline` - 确认内容
2. `full`（paged） - 逐页阅读

**预览式阅读**：
1. `full`（compressed） - 快速预览
2. `section` - 深入感兴趣的部分

## 性能考虑

### 各模式开销

| 模式 | 数据量 | 处理时间 | Token 消耗 |
|------|--------|---------|-----------|
| outline | 极小 | 极快 | 极低 |
| summary | 小 | 快 | 低 |
| section | 中 | 中 | 中 |
| snippets | 中 | 中 | 中 |
| full (strict) | 小/极小 | 快 | 低/极低 |
| full (paged) | 大 | 中 | 高（分次） |
| full (compressed) | 中 | 中 | 中 |

### 优化建议

1. **优先使用轻量级模式**
   - 先用 `outline`，再决定下一步
   - 避免直接使用 `full`

2. **合理配置 max_read_chars**
   - 根据 LLM 窗口大小设置
   - 避免过大或过小

3. **善用 section 模式**
   - 比 full 更节省资源
   - 更精确的内容获取

4. **分页要适度**
   - paged 模式会增加交互次数
   - 考虑使用 compressed 快速预览

## 故障排除

### 问题：outline 返回空白

**原因**：笔记没有标题

**解决**：使用 `full` 模式查看原始内容

### 问题：summary 返回空白

**原因**：笔记中没有标注块

**解决**：使用其他模式，或在笔记中添加标注

### 问题：section 返回不是期望的章节

**原因**：关键词匹配到其他章节

**解决**：使用更精确的关键词，或先用 `outline` 查看准确标题

### 问题：paged 模式页数太多

**原因**：`max_read_chars` 设置过小

**解决**：增加 `max_read_chars` 配置

### 问题：compressed 模式预览太短

**原因**：`compressed_section_preview_chars` 设置过小

**解决**：增加该配置值
