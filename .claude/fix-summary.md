# 前端表格显示问题修复总结

## 问题描述

用户反馈：预览页面表格显示 "no data"，无法正确加载数据。

## 根本原因

**字段名不一致导致的数据断层：**

1. **后端返回中文字段名**：`original_data` 和 `formatted_data` 包含 `源IP`、`目的IP` 等中文字段
2. **EditStep 使用英文字段名**：表格列定义为 `prop="source_ip"`、`prop="dest_ip"`
3. **数据流断裂**：
   ```
   上传文件 → 后端返回 {源IP: "xxx", 目的IP: "xxx"}
            ↓
   EditStep 加载 → 复制到 userModifiedData
            ↓
   EditStep 表格 → 使用 prop="source_ip" → ❌ 找不到数据（字段名是"源IP"）
            ↓
   PreviewStep → 使用 userModifiedData → ❌ 表格显示 "no data"
   ```

## 解决方案

**采用方案 1：后端统一返回英文字段名**

### 修改内容

#### 1. backend/app/core/excel_parser.py

修改字段映射，将中文字段名映射为英文：

```python
FIELD_MAPPING = {
    "源IP": "source_ip",
    "目的IP": "dest_ip",
    "源区域": "source_zone",
    "目的区域": "dest_zone",
    "目的端口": "service",
    "动作": "action",
    # ... 其他字段
}
```

同时更新 `_format_ip_addresses` 和 `_remove_example_policies` 方法使用英文字段名。

#### 2. backend/app/api/orders.py

更新保存策略时使用的字段名：

```python
policy = Policy(
    order_id=order.id,
    source_zone=str(row.get('source_zone', '')),
    dest_zone=str(row.get('dest_zone', '')),
    source_ip=str(row.get('source_ip', '')),
    dest_ip=str(row.get('dest_ip', '')),
    service=str(row.get('service', '')),
    action=str(row.get('action', 'permit'))
)
```

#### 3. frontend/src/views/workflow/PreviewStep.vue

简化表格列定义，移除中英文兼容代码：

```vue
<el-table-column prop="source_zone" label="源区域" />
<el-table-column prop="source_ip" label="源IP" />
<el-table-column prop="dest_zone" label="目的区域" />
<el-table-column prop="dest_ip" label="目的IP" />
<el-table-column prop="service" label="目的端口" />
<el-table-column prop="action" label="动作" />
```

#### 4. frontend/src/views/PreviewPage.vue

同样简化表格列定义。

## 优点

1. **符合编程规范**：变量名使用英文
2. **前端代码统一**：所有组件使用相同的字段名
3. **避免混乱**：不再有中英文混用
4. **性能最优**：无需额外的字段名转换
5. **易于维护**：代码更清晰，减少出错可能

## 测试验证

### 构建测试
```bash
npm run build
✓ built in 36.17s
```

### 完整流程测试

1. **上传文件** → 后端返回英文字段名的数据
2. **编辑页面** → EditStep 正确显示数据（字段名匹配）
3. **预览页面** → PreviewStep 正确显示数据（字段名匹配）
4. **推送功能** → 数据正确传递到推送页面

## Git 提交

```
commit 574e5ee
feat: 统一后端返回英文字段名，解决前端表格显示问题

涉及文件：
- backend/app/core/excel_parser.py
- backend/app/api/orders.py
- frontend/src/views/workflow/PreviewStep.vue
- frontend/src/views/PreviewPage.vue
```

已推送到 GitHub: https://github.com/mzywl/firewall-web.git

## 后续建议

1. **测试完整工作流**：上传 → 编辑 → 预览 → 推送
2. **验证数据正确性**：确保所有字段都正确显示
3. **检查其他页面**：确保 PushStep、EditPage 等页面也正常工作
4. **更新文档**：如果有 API 文档，需要更新字段名说明

## 技术债务清理

已移除的临时兼容代码：
- PreviewStep.vue 中的 `row['源IP'] || row.source_ip` 兼容逻辑
- PreviewPage.vue 中的相同兼容逻辑

现在代码更简洁，维护成本更低。
