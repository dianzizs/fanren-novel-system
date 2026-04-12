# 书目管理功能实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为小说工作台添加书目删除、来源标签、存储统计和按钮布局优化功能

**Architecture:** 后端在 api.py 添加 DELETE 接口和存储统计接口，service.py 添加删除逻辑；前端在藏书页面添加操作栏、删除按钮和存储显示

**Tech Stack:** Python FastAPI, JavaScript vanilla, CSS

---

## 文件变更概览

| 文件 | 变更类型 | 职责 |
|------|----------|------|
| `novel_system/models.py` | 修改 | BookInfo 添加 source 字段 |
| `novel_system/service.py` | 修改 | 添加 delete_book 和 storage_stats 方法 |
| `novel_system/api.py` | 修改 | 添加 DELETE /api/books/{book_id} 和 GET /api/storage-stats |
| `static/styles.css` | 修改 | 添加删除按钮、来源标签、存储统计样式 |
| `templates/dashboard.html` | 修改 | 添加操作栏和存储显示区域 |
| `static/app.js` | 修改 | 添加删除功能、存储统计显示 |

---

## Task 1: 模型添加 source 字段

**Files:**
- Modify: `novel_system/models.py:48-60` (BookInfo 类附近)

- [ ] **Step 1: 在 BookInfo 模型中添加 source 字段**

找到 BookInfo 类定义，在 `indexed_at` 字段后添加：

```python
class BookInfo(BaseModel):
    id: str
    title: str
    source_path: str | None = None
    chapter_count: int | None = None
    chunk_count: int | None = None
    indexed: bool = False
    indexed_at: datetime | None = None
    source: Literal["upload", "local"] = "local"  # 新增字段
```

- [ ] **Step 2: 提交**

```bash
git add novel_system/models.py
git commit -m "feat: add source field to BookInfo model"
```

---

## Task 2: Service 层添加删除和存储统计方法

**Files:**
- Modify: `novel_system/service.py:183` (list_books 方法后)

- [ ] **Step 1: 在 list_books 方法中添加 source 字段映射**

在 `list_books` 方法中，BookInfo 构造处添加 `source=manifest.get("source", "local")`

```python
books.append(
    BookInfo(
        id=manifest["id"],
        title=manifest["title"],
        source_path=manifest["source_path"],
        chapter_count=manifest.get("chapter_count", 0),
        chunk_count=manifest.get("chunk_count", 0),
        indexed=manifest.get("indexed", False),
        indexed_at=datetime.fromisoformat(indexed_at) if indexed_at else None,
        source=manifest.get("source", "local"),  # 新增
    )
)
```

- [ ] **Step 2: 添加 storage_stats 方法**

在 `list_books` 方法后添加：

```python
def get_storage_stats(self) -> dict[str, Any]:
    """获取存储统计信息"""
    stats = {
        "books": [],
        "total_index_size": 0,
        "total_uploads_size": 0,
    }
    for manifest in self.repo.list_books():
        book_id = manifest["id"]
        index_path = self.config.data_dir / "books" / book_id
        index_size = sum(f.stat().st_size for f in index_path.rglob("*") if f.is_file()) if index_path.exists() else 0
        stats["books"].append({
            "id": book_id,
            "title": manifest["title"],
            "index_size": index_size,
            "source": manifest.get("source", "local"),
        })
        stats["total_index_size"] += index_size

    uploads_path = self.config.data_dir / "uploads"
    if uploads_path.exists():
        stats["total_uploads_size"] = sum(f.stat().st_size for f in uploads_path.rglob("*") if f.is_file())
    return stats
```

- [ ] **Step 3: 添加 delete_book 方法**

在 `get_storage_stats` 方法后添加：

```python
def delete_book(self, book_id: str) -> dict[str, Any]:
    """删除书目及其关联数据"""
    manifest = next((book for book in self.repo.list_books() if book["id"] == book_id), None)
    if not manifest:
        raise FileNotFoundError(f"Book {book_id} not found")

    # 删除索引目录
    index_path = self.config.data_dir / "books" / book_id
    if index_path.exists():
        import shutil
        shutil.rmtree(index_path)

    # 如果是上传的书籍，删除源文件
    if manifest.get("source") == "upload":
        source_path = manifest.get("source_path")
        if source_path:
            p = Path(source_path)
            if p.exists():
                p.unlink()

    # 从 manifest 列表中移除
    self.repo.remove_book(book_id)

    return {"success": True, "book_id": book_id}
```

- [ ] **Step 4: 提交**

```bash
git add novel_system/service.py
git commit -m "feat: add storage_stats and delete_book methods"
```

---

## Task 3: Repository 层添加 remove_book 方法

**Files:**
- Modify: `novel_system/indexing.py` (BookIndexRepository 类)

- [ ] **Step 1: 找到 BookIndexRepository 类中的 list_books 方法**

- [ ] **Step 2: 在 list_books 方法后添加 remove_book 方法**

```python
def remove_book(self, book_id: str) -> None:
    """从 manifest 中移除书目"""
    manifest_path = self.manifest_path()
    if not manifest_path.exists():
        return
    books = [b for b in self.list_books() if b["id"] != book_id]
    manifest_path.write_text(json.dumps({"books": books}, ensure_ascii=False, indent=2), encoding="utf-8")
```

- [ ] **Step 3: 提交**

```bash
git add novel_system/indexing.py
git commit -m "feat: add remove_book method to repository"
```

---

## Task 4: API 层添加删除和存储统计接口

**Files:**
- Modify: `novel_system/api.py:43-66`

- [ ] **Step 1: 在 list_books 后添加 storage-stats 和 delete 接口**

在 `@app.get("/api/books")` 之后，`@app.post("/api/books")` 之前添加：

```python
@app.get("/api/storage-stats")
async def get_storage_stats():
    return service.get_storage_stats()

@app.delete("/api/books/{book_id}")
async def delete_book(book_id: str):
    try:
        return service.delete_book(book_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
```

- [ ] **Step 2: 修改 POST /api/books 注册时标记 source**

在 `register_book` 函数中，ensure_book_manifest 调用处添加 source 参数：

文件上传时：`manifest = service.repo.ensure_book_manifest(book_id, title or file.filename, str(target_path), source="upload")`

文件路径注册时：`manifest = service.repo.ensure_book_manifest(book_id, title or chosen_path.stem, str(chosen_path), source="local")`

- [ ] **Step 3: 确保 remove_book 方法接受额外参数**

检查 `ensure_book_manifest` 方法签名，如果需要修改以接受 `source` 参数。

- [ ] **Step 4: 提交**

```bash
git add novel_system/api.py
git commit -m "feat: add DELETE /api/books and GET /api/storage-stats endpoints"
```

---

## Task 5: CSS 样式添加

**Files:**
- Modify: `static/styles.css` (文件末尾，@media 查询之前)

- [ ] **Step 1: 添加操作栏样式**

```css
/* 藏书页操作栏 */
.library-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}

.library-actions-left {
  display: flex;
  gap: 10px;
}

.storage-stats {
  display: flex;
  gap: 16px;
  font-size: 13px;
  color: var(--muted);
}

.storage-stats span {
  padding: 6px 12px;
  background: var(--surface);
  border-radius: var(--radius-sm);
}

/* 来源标签 */
.source-tag {
  display: inline-flex;
  padding: 3px 8px;
  border-radius: var(--radius-sm);
  font-size: 11px;
  font-weight: 500;
}

.source-tag.upload {
  color: #74b9ff;
  background: rgba(116, 185, 255, 0.15);
  border: 1px solid rgba(116, 185, 255, 0.3);
}

.source-tag.local {
  color: var(--accent);
  background: rgba(116, 225, 184, 0.12);
  border: 1px solid rgba(116, 225, 184, 0.24);
}

/* 书卡删除按钮 */
.book-card {
  position: relative;
}

.book-card-actions {
  position: absolute;
  top: 12px;
  right: 12px;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.book-card:hover .book-card-actions {
  opacity: 1;
}

.delete-book-btn {
  padding: 6px 10px;
  background: rgba(255, 126, 139, 0.15);
  border: 1px solid rgba(255, 126, 139, 0.3);
  color: var(--accent-strong);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 12px;
}

.delete-book-btn:hover {
  background: rgba(255, 126, 139, 0.25);
}

/* 确认对话框 */
.confirm-dialog-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.confirm-dialog {
  background: var(--bg-elevated);
  border: 1px solid var(--line-strong);
  border-radius: var(--radius-lg);
  padding: 24px;
  max-width: 400px;
  box-shadow: var(--shadow);
}

.confirm-dialog h3 {
  margin-bottom: 12px;
}

.confirm-dialog p {
  color: var(--muted);
  margin-bottom: 20px;
}

.confirm-dialog-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
}
```

- [ ] **Step 2: 提交**

```bash
git add static/styles.css
git commit -m "feat: add styles for book management UI"
```

---

## Task 6: HTML 模板修改

**Files:**
- Modify: `templates/dashboard.html` (藏书 section)

- [ ] **Step 1: 在藏书 section-head 中添操作栏**

将：
```html
<div class="section-head">
  <div>
    <h2>藏书</h2>
    <p>查看当前项目书目、索引状态、章节规模和切片数量。</p>
  </div>
</div>
```

改为：
```html
<div class="section-head">
  <div>
    <h2>藏书</h2>
    <p>查看当前项目书目、索引状态、章节规模和切片数量。</p>
  </div>
</div>
<div class="library-actions">
  <div class="library-actions-left">
    <button id="import-book-btn" class="primary">导入新书</button>
    <button id="refresh-books-btn" class="secondary">刷新书库</button>
  </div>
  <div class="storage-stats" id="storage-stats">
    <span>索引存储：<strong id="index-size">-</strong></span>
    <span>上传文件：<strong id="uploads-size">-</strong></span>
  </div>
</div>
```

- [ ] **Step 2: 提交**

```bash
git add templates/dashboard.html
git commit -m "feat: add library actions bar and storage stats to dashboard"
```

---

## Task 7: JavaScript 功能实现

**Files:**
- Modify: `static/app.js` (bindEvents 函数附近)

- [ ] **Step 1: 添加 storage 格式化辅助函数**

在 `escapeHtml` 函数后添加：

```javascript
function formatBytes(bytes) {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}
```

- [ ] **Step 2: 修改 loadBooks 函数，添加来源标签和删除按钮**

在 `loadBooks` 函数的书卡渲染部分（`bookCards.innerHTML = books.map...`），修改渲染模板：

```javascript
bookCards.innerHTML = books.map((book) => {
  const isActive = String(book.id) === String(bookId);
  const indexed = Boolean(book.indexed);
  const sourceTag = book.source === "upload"
    ? '<span class="source-tag upload">本地上传</span>'
    : '<span class="source-tag local">原书</span>';
  return `
    <div class="book-card ${isActive ? "active" : ""}">
      <div class="book-card-actions">
        <button class="delete-book-btn" data-book-id="${escapeHtml(book.id)}" data-book-title="${escapeHtml(book.title)}">删除</button>
      </div>
      <div class="status-row">
        <span class="status-tag ${indexed ? "" : "pending"}">${indexed ? "已索引" : "待处理"}</span>
        ${sourceTag}
        ${isActive ? "<span class='mini-tag'>当前工作本</span>" : ""}
      </div>
      <h3>${escapeHtml(book.title)}</h3>
      <div class="book-meta">ID：${escapeHtml(book.id)}</div>
      <div class="book-meta">章节数：${escapeHtml(book.chapter_count || "-")}</div>
      <div class="book-meta">切片数：${escapeHtml(book.chunk_count || "-")}</div>
      <div class="book-meta">${escapeHtml(book.source_path || "未记录来源路径")}</div>
    </div>
  `;
}).join("");
```

- [ ] **Step 3: 添加 loadStorageStats 函数**

在 `loadBooks` 函数后添加：

```javascript
async function loadStorageStats() {
  try {
    const stats = await fetchJson("/api/storage-stats");
    $("#index-size").textContent = formatBytes(stats.total_index_size || 0);
    $("#uploads-size").textContent = formatBytes(stats.total_uploads_size || 0);
  } catch (error) {
    console.error("Failed to load storage stats:", error);
  }
}
```

- [ ] **Step 4: 添加删除确认对话框函数**

在 `loadStorageStats` 后添加：

```javascript
function showDeleteConfirmDialog(bookId, bookTitle) {
  const overlay = document.createElement("div");
  overlay.className = "confirm-dialog-overlay";
  overlay.innerHTML = `
    <div class="confirm-dialog">
      <h3>确认删除</h3>
      <p>确定删除《${escapeHtml(bookTitle)}》吗？此操作不可恢复，所有索引数据将被删除。</p>
      <div class="confirm-dialog-actions">
        <button class="secondary" id="cancel-delete-btn">取消</button>
        <button class="primary" id="confirm-delete-btn" data-book-id="${escapeHtml(bookId)}">确认删除</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  $("#cancel-delete-btn").addEventListener("click", () => overlay.remove());
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) overlay.remove();
  });
  $("#confirm-delete-btn").addEventListener("click", async () => {
    const btn = $("#confirm-delete-btn");
    btn.disabled = true;
    btn.textContent = "删除中...";
    try {
      await fetchJson(`/api/books/${btn.dataset.bookId}`, { method: "DELETE" });
      overlay.remove();
      await loadBooks();
      await loadStorageStats();
      setWorkspaceStatus("书目已删除", "ready");
    } catch (error) {
      handleActionError(error, null, "删除失败");
      btn.disabled = false;
      btn.textContent = "确认删除";
    }
  });
}
```

- [ ] **Step 5: 修改 bindEvents 函数，添加删除和导入事件**

在 bindEvents 函数中添加：

```javascript
// 删除按钮事件
document.addEventListener("click", (e) => {
  if (e.target.classList.contains("delete-book-btn")) {
    const btn = e.target;
    showDeleteConfirmDialog(btn.dataset.bookId, btn.dataset.bookTitle);
  }
});

// 刷新书库按钮
$("#refresh-books-btn")?.addEventListener("click", async () => {
  const btn = $("#refresh-books-btn");
  setButtonLoading(btn, true, "刷新中...");
  try {
    await loadBooks();
    await loadStorageStats();
    setWorkspaceStatus("书库已刷新", "ready");
  } catch (error) {
    handleActionError(error, "#book-cards", "刷新失败");
  } finally {
    setButtonLoading(btn, false, "刷新中...");
  }
});

// 导入新书按钮
$("#import-book-btn")?.addEventListener("click", () => {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = ".txt";
  input.addEventListener("change", async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);
    try {
      const response = await fetch("/api/books", { method: "POST", body: formData });
      if (response.ok) {
        await loadBooks();
        await loadStorageStats();
        setWorkspaceStatus("新书已导入", "ready");
      }
    } catch (error) {
      handleActionError(error, "#book-cards", "导入失败");
    }
  });
  input.click();
});
```

- [ ] **Step 6: 修改 bootstrap 函数，添加存储统计加载**

在 bootstrap 函数中，在 `loadBooks()` 调用后添加 `loadStorageStats()`：

```javascript
try {
  await loadBooks();
  await loadStorageStats();  // 新增
  await loadReader(1);
  await loadDashboard();
  await loadGraph();
  setWorkspaceStatus("工作区已就绪", "ready");
} catch (error) {
  handleActionError(error, "#book-cards", "初始化失败");
}
```

- [ ] **Step 7: 提交**

```bash
git add static/app.js
git commit -m "feat: add book management UI interactions"
```

---

## Task 8: 整体测试

- [ ] **Step 1: 启动服务器**

```bash
cd D:\projects\小王一号 && python -m scripts.run_api
```

- [ ] **Step 2: 测试存储统计 API**

```bash
curl http://localhost:18792/api/storage-stats
```

预期：返回 JSON 包含 total_index_size, total_uploads_size, books 数组

- [ ] **Step 3: 测试删除 API（用测试书籍）**

```bash
# 先创建测试书籍
curl -X POST "http://localhost:18792/api/books?title=test&file_path=D:\test.txt"

# 删除测试书籍
curl -X DELETE http://localhost:18792/api/books/test
```

- [ ] **Step 4: 浏览器测试**

1. 打开 http://localhost:18792/
2. 藏书页面应显示「导入新书」「刷新书库」按钮
3. 书卡应显示来源标签（本地上传/原书）
4. 存储统计应显示索引和上传大小
5. Hover 书卡应显示删除按钮
6. 点击删除应弹出确认对话框

---

## 验收标准

1. ✅ `DELETE /api/books/{book_id}` 返回 `{success: true}`
2. ✅ `GET /api/storage-stats` 返回存储统计
3. ✅ 藏书页面显示存储使用量
4. ✅ 书卡显示来源标签
5. ✅ 删除按钮可弹出确认对话框
6. ✅ 确认删除后书目从列表移除
7. ✅ 上传的文件被删除后，源文件同步删除

---

**Plan complete.** 建议使用 **Subagent-Driven** 方式执行，每个 Task 由独立 subagent 完成，便于审查和修改。
