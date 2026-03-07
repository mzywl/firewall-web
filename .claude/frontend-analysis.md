# 前端表格加载问题完整分析

## 问题现象
预览页面表格显示 "no data"，无法正确加载数据。

## 根本原因分析

### 1. 数据流问题

**后端返回的数据结构：**
```json
{
  "id": 1,
  "order_no": "ORD-xxx",
  "title": "文件名",
  "original_data": [
    {"源IP": "xxx", "目的IP": "xxx", ...}  // 中文字段名
  ],
  "formatted_data": [
    {"源IP": "xxx", "目的IP": "xxx", ...}  // 中文字段名
  ]
}
```

**EditStep 使用的字段名：**
```typescript
// EditStep.vue 使用英文字段名
<el-table-column prop="source_ip" label="源IP" />
<el-table-column prop="dest_ip" label="目的IP" />
```

**PreviewStep 期望的字段名：**
```vue
<!-- PreviewStep.vue 同时支持中英文 -->
<template #default="{ row }">
  {{ row['源IP'] || row.source_ip || '' }}
</template>
```

### 2. 核心矛盾

1. **后端返回中文字段名**：`original_data` 和 `formatted_data` 都是中文字段
2. **EditStep 使用英文字段名**：用户在编辑页面修改数据时，使用的是英文字段
3. **PreviewStep 数据来源**：
   ```typescript
   const data = orderStore.currentOrder.userModifiedData.length > 0
     ? orderStore.currentOrder.userModifiedData  // 优先使用用户修改的数据（英文字段）
     : orderStore.currentOrder.formattedData     // 回退到格式化数据（中文字段）
   ```

### 3. 问题场景

**场景 A：直接从上传跳到预览**
- 数据来源：`formattedData`（中文字段）
- 结果：✅ 可以显示（因为 PreviewStep 支持中文字段）

**场景 B：上传 → 编辑 → 预览**
- 数据来源：`userModifiedData`（英文字段）
- 结果：✅ 可以显示（因为 PreviewStep 支持英文字段）

**场景 C：上传 → 编辑（未修改）→ 预览**
- EditStep 初始化时：
  ```typescript
  if (orderStore.currentOrder.userModifiedData.length > 0) {
    userModifiedData.value = [...orderStore.currentOrder.userModifiedData]
  } else {
    // 复制 formattedData（中文字段）到 userModifiedData
    userModifiedData.value = JSON.parse(JSON.stringify(formattedData.value))
    orderStore.setUserModifiedData(userModifiedData.value)
  }
  ```
- 问题：`formattedData` 是中文字段，但 EditStep 的表格使用 `prop="source_ip"` 等英文字段
- 结果：❌ EditStep 表格显示空白，PreviewStep 也显示空白

## 根本问题

**字段名不一致导致的数据断层：**

1. 后端返回中文字段名（`源IP`, `目的IP`）
2. EditStep 期望英文字段名（`source_ip`, `dest_ip`）
3. 数据在 EditStep 和 PreviewStep 之间传递时字段名不匹配

## 解决方案

### 方案 1：后端统一返回英文字段名（推荐）

**优点：**
- 前端代码统一使用英文字段，符合编程规范
- 避免中英文混用导致的混乱
- 性能最优，无需额外转换

**修改点：**
```python
# backend/app/core/excel_parser.py
# 在 _normalize_field_names 方法中，将中文字段名映射为英文
FIELD_MAPPING = {
    "源IP": "source_ip",
    "目的IP": "dest_ip",
    "源区域": "source_zone",
    "目的区域": "dest_zone",
    "目的端口": "service",
    "动作": "action"
}
```

### 方案 2：前端统一使用中文字段名

**优点：**
- 与后端保持一致
- 无需修改后端代码

**缺点：**
- 违反编程规范（变量名应使用英文）
- 代码可读性差

**修改点：**
```vue
<!-- EditStep.vue -->
<el-table-column prop="源IP" label="源IP" />
<el-table-column prop="目的IP" label="目的IP" />
```

### 方案 3：前端添加字段名转换层

**优点：**
- 前后端都不需要大改
- 灵活性高

**缺点：**
- 增加复杂度
- 性能开销

**实现：**
```typescript
// 在 UploadStep 中转换字段名
const convertToEnglish = (data: any[]) => {
  return data.map(row => ({
    source_ip: row['源IP'] || row.source_ip || '',
    dest_ip: row['目的IP'] || row.dest_ip || '',
    source_zone: row['源区域'] || row.source_zone || '',
    dest_zone: row['目的区域'] || row.dest_zone || '',
    service: row['目的端口'] || row.service || '',
    action: row['动作'] || row.action || ''
  }))
}

orderStore.setFormattedData(convertToEnglish(response.formatted_data))
```

## 推荐方案

**采用方案 1：后端统一返回英文字段名**

理由：
1. 符合编程规范
2. 前端代码更清晰
3. 避免中英文混用
4. 性能最优
5. 易于维护

## 实施步骤

1. 修改 `backend/app/core/excel_parser.py` 的字段映射
2. 修改 `backend/app/api/orders.py` 中保存策略时的字段名
3. 更新 PreviewStep.vue，移除中文字段的兼容代码
4. 测试完整流程：上传 → 编辑 → 预览 → 推送
