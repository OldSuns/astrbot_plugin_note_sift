# 故障排除

本文档提供 NoteSift 常见问题的解决方案。

## 导入问题

### 导入失败：zip 文件不存在

**错误信息**：
```
zip file not found: /path/to/vault.zip
```

**原因**：
- 文件路径错误
- 文件已被移动或删除
- 权限不足

**解决方案**：
1. 检查配置中的路径是否正确
2. 确认文件确实存在
3. 检查文件读取权限
4. 使用绝对路径而非相对路径

### 导入失败：没有可导入的文件

**现象**：
- 导入完成但 file_count = 0
- status 显示知识库为空

**原因**：
- zip 中不包含支持的文件类型
- 文件扩展名不在允许列表
- 文件大小超过限制

**解决方案**：
1. 检查 zip 中是否包含 `.md`, `.markdown`, `.txt` 文件
2. 确认文件扩展名正确
3. 检查文件大小是否超过配置限制（默认 5MB）
4. 查看日志中的 ignored_count

### 导入后 zip 文件被删除

**现象**：
- 导入成功后 zip 文件不见了

**说明**：
- 这是**预期行为**
- 导入成功后自动删除 zip 以节省空间

**预防措施**：
- 导入前备份 zip 文件
- 或保留原始笔记目录

### Obsidian vault 导入异常

**现象**：
- 包含 `.obsidian` 的 zip 导入后文件数不符

**原因**：
- 自动检测到 `.obsidian` 目录
- 仅导入该目录下的内容

**说明**：
- 这是**预期行为**
- 自动识别 Obsidian vault root

**示例**：
```
zip 结构：
  outer/readme.md
  vault/.obsidian/app.json
  vault/notes/note1.md

结果：
  仅导入 vault/notes/note1.md
  忽略 outer/readme.md
```

## 搜索问题

### 搜索返回空结果

**原因 1：知识库未导入**

**检查**：
```bash
/kb status
```

**解决**：
- 确认 manifest 和 index 存在
- 重新导入：`/kb rebuild`

**原因 2：查询词不存在**

**检查**：
- 尝试更通用的关键词
- 使用 `/kb grep` 在正文中搜索

**原因 3：vault_id 错误**

**检查**：
```bash
/kb status  # 查看所有 vault_id
```

**解决**：
- 使用正确的 vault_id
- 或不指定 vault_id 进行跨库搜索

### 搜索结果不准确

**原因**：
- 多词查询要求所有词都存在
- 权重机制导致排序不符预期

**解决**：
- 使用更精确的关键词
- 减少查询词数量
- 检查命中字段（matched_fields）

### 正文搜索（grep）无结果

**与 discover 的区别**：
- grep 仅搜索正文
- discover 搜索所有字段

**解决**：
- 如果内容在标题/标签中，使用 discover
- 或确认正文中确实存在该内容

## 读取问题

### 读取失败：笔记不存在

**错误**：
```
found: false
error: note not found
```

**原因**：
- note_id 错误
- vault_id 错误
- 笔记已被删除

**解决**：
1. 确认 note_id 正确（从搜索结果获取）
2. 检查 vault_id 是否匹配
3. 重新搜索获取最新 note_id

### 内容被截断

**现象**：
```
truncated: true
next_action_hint: "Content exceeds max_read_chars. Read a specific section by heading."
```

**原因**：
- 内容超过 `max_read_chars`
- 使用 strict 策略

**解决方案**：

**方案 1：增加限制**
```json
{
  "max_read_chars": 15000
}
```

**方案 2：使用 paged 模式**
```json
{
  "full_over_limit_strategy": "paged"
}
```
```bash
/kb read 1 full 1
/kb read 1 full 2
```

**方案 3：使用 section 模式**
```bash
/kb read 1 outline  # 先查看结构
# 根据标题读取需要的章节
```

**方案 4：使用 compressed 模式**
```json
{
  "full_over_limit_strategy": "compressed"
}
```

### paged 模式页数过多

**原因**：
- `max_read_chars` 设置过小
- 内容确实很长

**解决**：
1. 增加 `max_read_chars`
2. 使用 section 模式读取特定章节
3. 使用 compressed 模式快速预览

### compressed 模式预览太短

**原因**：
- `compressed_section_preview_chars` 设置过小

**解决**：
```json
{
  "compressed_section_preview_chars": 300
}
```

建议范围：100-500

### section 模式返回错误章节

**原因**：
- heading 参数匹配到其他章节
- 多个章节包含相同关键词

**解决**：
1. 先用 outline 模式查看准确标题
2. 使用更完整的标题关键词
3. 使用更具体的标题

**示例**：
```python
# 不好：太通用
kb_read(note_id, mode="section", heading="介绍")

# 好：更具体
kb_read(note_id, mode="section", heading="IVIG治疗介绍")
```

## 配置问题

### ACL 不生效

**现象**：
- 设置了白名单但所有人都能访问
- 或设置了白名单但谁都访问不了

**检查**：
1. `enable_acl` 是否为 `true`
2. `allowed_sessions` 格式是否正确（每行一个）
3. UMO 是否与实际会话匹配

**正确格式**：
```json
{
  "enable_acl": true,
  "allowed_sessions": "qq_12345\nwechat_67890"
}
```

### 配置更新不生效

**原因**：
- 配置未保存
- 需要重启 AstrBot
- 需要重建索引

**解决**：
1. 保存配置
2. 重启 AstrBot
3. 对于知识库配置，执行 `/kb rebuild`

### 自定义数据目录不生效

**检查**：
1. 路径是否正确
2. 目录是否存在
3. 是否有写权限

**解决**：
```json
{
  "custom_data_dir": "/absolute/path/to/data"
}
```
- 使用绝对路径
- 确保目录存在
- 确保有读写权限

## 权限问题

### 命令被拒绝

**错误**：
```
当前会话未授权访问知识库。
```

**原因**：
- ACL 已启用
- 当前会话不在白名单

**解决**：
1. 确认是否需要 ACL
2. 如不需要，设置 `enable_acl: false`
3. 如需要，将会话添加到白名单

### rebuild 命令无权限

**错误**：
```
权限不足
```

**原因**：
- rebuild 需要管理员权限

**解决**：
- 使用管理员账号执行
- 或联系管理员执行

## 性能问题

### 搜索速度慢

**原因**：
- 知识库过大
- 跨多个库搜索
- FTS5 不可用

**解决**：

**方案 1：指定库搜索**
```python
# 不好
kb_discover("keyword")  # 搜索所有库

# 好
kb_discover("keyword", vault_id="specific")
```

**方案 2：减少库数量**
- 合并相关的小库
- 拆分过大的库

**方案 3：检查 FTS5**
```bash
/kb status  # 查看 FTS5 是否可用
```

### 读取速度慢

**原因**：
- 文件过大
- 使用 full 模式

**解决**：
1. 优先使用 outline, summary
2. 使用 section 读取特定部分
3. 增加 `max_read_chars` 避免频繁分页

### 内存占用高

**原因**：
- 索引数据库过大
- 缓存过多

**解决**：
1. 定期清理无用知识库
2. 拆分超大知识库
3. 重启 AstrBot 释放缓存

## 数据问题

### 数据丢失

**预防**：
- 定期备份原始 zip 文件
- 或备份 data_dir/vaults 目录（包含 files/ 和索引）

**恢复**：

**方案 1：从 zip 恢复**
1. 恢复原始 zip 文件
2. 重新上传 zip 导入

**方案 2：从 files/ 恢复**
1. 恢复备份的 vaults 目录
2. 执行 `/kb rebuild` 重建索引

**说明**：
- files/ 目录包含所有导入的 Markdown 文件
- 索引可以从 files/ 重建
- zip 文件仅在导入时需要

### 索引损坏

**现象**：
- 搜索结果异常
- 读取报错
- status 显示异常

**解决**：
```bash
/kb rebuild  # 重建所有库
# 或
/kb rebuild vault_id  # 重建特定库
```

**说明**：
- rebuild 从已有的 files/ 目录重建索引
- 不需要原始 zip 文件
- 不影响已导入的文件

### 中文乱码

**原因**：
- 文件编码不是 UTF-8

**解决**：
1. 转换文件为 UTF-8 编码
2. 重新打包 zip
3. 重新导入

## 兼容性问题

### SQLite FTS5 不可用

**现象**：
```bash
/kb status
# 显示 FTS5: 不可用
```

**影响**：
- 搜索速度可能较慢
- 功能正常，自动降级

**说明**：
- 自动降级到普通 SQL 搜索
- 不影响基本功能

### Obsidian 格式问题

**支持的格式**：
- 标准 Markdown
- Obsidian callout（标注块）
- 基础的 Obsidian 语法

**不支持的格式**：
- Obsidian 插件扩展语法
- Dataview 查询
- 复杂的嵌入

**解决**：
- 使用标准 Markdown 语法
- 移除不支持的扩展语法

## 调试技巧

### 查看详细状态

```bash
/kb status
```
- 检查所有知识库状态
- 确认 manifest 和 index 存在
- 查看文件存储路径

### 测试单个库

```bash
# 搜索
/kb search vault_id:test

# 读取
/kb read vault_id:note.md
```

### 检查日志

查看 AstrBot 日志中的：
- 导入警告
- 搜索错误
- 读取异常

### 重建索引

```bash
# 重建所有
/kb rebuild

# 重建特定库
/kb rebuild vault_id
```

### 清理重试

1. 删除数据目录
2. 重新配置
3. 重新导入

```bash
# 删除所有知识库数据
rm -rf /data/astrbot/plugin_data/note_sift/vaults

# 重新导入
/kb rebuild
```

## 获取帮助

### 问题无法解决？

1. 检查本文档相关章节
2. 查看 AstrBot 日志
3. 在插件仓库提交 Issue

### 提交 Issue 时提供：

- 详细的错误信息
- `/kb status` 输出
- 配置信息（隐藏敏感路径）
- AstrBot 版本
- 复现步骤

### 有用的调试信息：

```bash
# 1. 知识库状态
/kb status

# 2. 测试搜索
/kb search test

# 3. 测试读取
/kb read 1 outline

# 4. 查看配置
cat config.json  # 配置文件位置
```
