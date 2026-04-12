# 书目管理功能改进设计

## 概述
为《凡人修仙传》长篇小说工作台添加书目管理功能，包括删除、来源区分、存储统计和按钮布局优化。

## 1. 删除书目功能

### 后端
- **API**: `DELETE /api/books/{book_id}`
- **行为**:
  1. 从 manifest 列表中移除书目记录
  2. 删除 `data/books/{book_id}/` 目录（索引数据）
  3. 如果是上传的书籍（source=upload），同时删除 `data/uploads/` 中的源文件
- **返回**: `{ success: true }` 或错误信息

### 前端
- 在书卡右上角添加删除按钮（垃圾桶图标）
- 点击后弹出确认对话框：「确定删除《XXX》吗？此操作不可恢复。」
- 确认后执行删除，刷新书库列表

## 2. 来源标签

### 数据模型
- 上传的文件：`source: "upload"`
- 注册的原书：`source: "local"`

### 前端显示
- 书卡上显示彩色标签：「本地上传」或「原书」
- 不同颜色区分：upload=蓝色，local=绿色

## 3. 存储统计

### 后端
- 新增 `GET /api/storage-stats`
- 返回：
  ```json
  {
    "total_uploads_size": 12345678,
    "total_index_size": 98765432,
    "books": [
      { "id": "fanren", "title": "凡人修仙传", "index_size": 98765432 }
    ]
  }
  ```

### 前端
- 在藏书页面顶部显示存储使用量
- 格式：「索引存储：XX MB | 上传文件：XX MB」

## 4. 按钮布局优化

### 藏书页面顶部操作栏
```
[导入新书] [刷新书库]          索引存储：XX MB | 上传文件：XX MB
```

### 书卡操作
- 右上角放置删除按钮（hover 时显示）
- 当前书籍标记「当前工作本」

## 文件变更

### 后端
- `novel_system/api.py`: 添加 DELETE 接口和存储统计接口
- `novel_system/service.py`: 添加删除逻辑和存储计算

### 前端
- `static/app.js`: 添加删除功能、存储统计显示
- `static/styles.css`: 添加删除按钮样式、存储统计样式
- `templates/dashboard.html`: 添加操作栏和存储显示区域

## 优先级
1. 删除功能（核心）
2. 来源标签（高）
3. 存储统计（中）
4. 按钮布局优化（中）
