# 书籍导入与详情页实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现书籍上传后半自动进入详情分析流程，包含进度展示和实时图谱更新

**Architecture:** 后端添加状态管理和进度 API，前端实现 hash-based 路由跳转详情页，轮询更新进度

**Tech Stack:** Python FastAPI, JavaScript vanilla, CSS

---

## 文件变更概览

| 文件 | 变更类型 | 职责 |
|------|----------|------|
| `novel_system/models.py` | 修改 | BookInfo 添加 status, index_progress 字段 |
| `novel_system/service.py` | 修改 | 添加 get_book_status, start_book_index, set_book_indexing 方法 |
| `novel_system/api.py` | 修改 | 添加 /api/books/{book_id}/status 和 /api/books/{book_id}/start-index 端点 |
| `static/app.js` | 修改 | 添加路由逻辑、详情页渲染、进度轮询 |
| `static/styles.css` | 修改 | 添加详情页样式 |
| `templates/dashboard.html` | 修改 | 添加详情页模板容器 |

---

## Task 1: 模型添加状态字段

**Files:**
- Modify: `novel_system/models.py` (BookInfo 类附近)

- [ ] **Step 1: 修改 BookInfo 模型添加状态字段**

找到 BookInfo 类，添加 status 和 index_progress 字段：

```python
class BookInfo(BaseModel):
    id: str
    title: str
    source_path: str
    source: Literal["upload", "local"] = "local"
    chapter_count: int = 0
    chunk_count: int = 0
    indexed: bool = False
    indexed_at: datetime | None = None
    status: Literal["pending", "indexing", "ready", "error"] = "pending"
    index_progress: float = 0.0
```

- [ ] **Step 2: 提交**

```bash
git add novel_system/models.py && git commit -m "feat: add status and index_progress fields to BookInfo"
```

---

## Task 2: Service 层添加状态管理方法

**Files:**
- Modify: `novel_system/service.py`

- [ ] **Step 1: 添加 get_book_status 方法**

在 `get_token_stats` 方法后添加：

```python
def get_book_status(self, book_id: str) -> dict[str, Any]:
    """获取书籍索引状态"""
    manifest = next((book for book in self.repo.list_books() if book["id"] == book_id), None)
    if not manifest:
        raise FileNotFoundError(f"Book {book_id} not found")
    return {
        "book_id": book_id,
        "status": manifest.get("status", "pending"),
        "progress": manifest.get("index_progress", 0.0),
        "message": self._get_status_message(manifest),
    }

def _get_status_message(self, manifest: dict[str, Any]) -> str:
    """获取状态描述"""
    status = manifest.get("status", "pending")
    if status == "pending":
        return "等待开始分析"
    elif status == "indexing":
        progress = manifest.get("index_progress", 0)
        return f"正在分析... ({int(progress * 100)}%)"
    elif status == "ready":
        return "分析完成"
    elif status == "error":
        return "分析失败"
    return "未知状态"
```

- [ ] **Step 2: 添加 set_book_indexing 方法（内部更新状态）**

在 `get_book_status` 后添加：

```python
def set_book_indexing(self, book_id: str, status: str, progress: float = 0.0) -> None:
    """更新书籍索引状态"""
    manifest = next((book for book in self.repo.list_books() if book["id"] == book_id), None)
    if not manifest:
        return
    manifest["status"] = status
    manifest["index_progress"] = progress
    if status == "ready":
        manifest["indexed"] = True
        manifest["indexed_at"] = datetime.now().isoformat()
    self.repo.update_book_manifest(book_id, manifest)
```

- [ ] **Step 3: 添加 start_book_index 方法**

在 `set_book_indexing` 后添加：

```python
def start_book_index(self, book_id: str) -> dict[str, Any]:
    """开始索引书籍（后台运行）"""
    manifest = next((book for book in self.repo.list_books() if book["id"] == book_id), None)
    if not manifest:
        raise FileNotFoundError(f"Book {book_id} not found")

    if manifest.get("status") == "indexing":
        return {"status": "indexing", "message": "正在分析中"}

    if manifest.get("status") == "ready":
        return {"status": "ready", "message": "已经分析完成"}

    # 设置为索引中状态
    self.set_book_indexing(book_id, "indexing", 0.0)

    # TODO: 实际索引工作将由前端轮询触发或后台任务处理
    # 这里先标记为开始，实际索引在后续 Task 中完善

    return {"status": "indexing", "message": "开始分析"}
```

- [ ] **Step 4: 修改 list_books 返回状态信息**

找到 `list_books` 方法中的 BookInfo 构造，添加 status 和 index_progress：

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
        source=manifest.get("source", "local"),
        status=manifest.get("status", "pending"),
        index_progress=manifest.get("index_progress", 0.0),
    )
)
```

- [ ] **Step 5: 提交**

```bash
git add novel_system/service.py && git commit -m "feat: add book status management methods"
```

---

## Task 3: Repository 层添加 update_book_manifest 方法

**Files:**
- Modify: `novel_system/indexing.py`

- [ ] **Step 1: 添加 update_book_manifest 方法**

在 `remove_book` 方法后添加：

```python
def update_book_manifest(self, book_id: str, manifest: dict[str, Any]) -> None:
    """更新书籍 manifest"""
    book_dir = self._book_dir(book_id)
    manifest_path = book_dir / "manifest.json"
    if not manifest_path.exists():
        return
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
```

- [ ] **Step 2: 提交**

```bash
git add novel_system/indexing.py && git commit -m "feat: add update_book_manifest method"
```

---

## Task 4: API 层添加状态和启动索引接口

**Files:**
- Modify: `novel_system/api.py`

- [ ] **Step 1: 添加 status 和 start-index 端点**

在 `GET /api/books/{book_id}/reader` 端点之前添加：

```python
@app.get("/api/books/{book_id}/status")
async def get_book_status(book_id: str):
    try:
        return service.get_book_status(book_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.post("/api/books/{book_id}/start-index")
async def start_book_index(book_id: str):
    try:
        return service.start_book_index(book_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
```

- [ ] **Step 2: 修改 POST /api/books 设置初始状态**

找到 `register_book` 中的 `ensure_book_manifest` 调用，添加 `status="pending"` 参数：

文件上传时：`manifest = service.repo.ensure_book_manifest(book_id, title or file.filename, str(target_path), source="upload")`
路径注册时：`manifest = service.repo.ensure_book_manifest(book_id, title or chosen_path.stem, str(chosen_path), source="local")`

需要修改 indexing.py 的 ensure_book_manifest 接受 status 参数。

- [ ] **Step 3: 提交**

```bash
git add novel_system/api.py && git commit -m "feat: add book status and start-index API endpoints"
```

---

## Task 5: 前端路由和藏书页改动

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: 添加路由状态管理**

在文件顶部变量定义区域添加：

```javascript
const router = {
  currentView: "library",  // "library" or "detail"
  currentBookId: null,
};
```

- [ ] **Step 2: 添加 hash 路由监听**

在 `bootstrap` 函数前添加：

```javascript
function initRouter() {
  window.addEventListener("hashchange", handleRouteChange);
  handleRouteChange();
}

function handleRouteChange() {
  const hash = window.location.hash || "#/";
  if (hash.startsWith("#/book/")) {
    const bookId = hash.replace("#/book/", "");
    router.currentView = "detail";
    router.currentBookId = bookId;
    showBookDetail(bookId);
  } else {
    router.currentView = "library";
    router.currentBookId = null;
    showLibraryView();
  }
}

function navigateTo(path) {
  window.location.hash = path;
}

function showLibraryView() {
  // 显示藏书列表视图
  // 隐藏详情视图
}

function showBookDetail(bookId) {
  // 显示详情视图
  // 隐藏藏书列表视图
}
```

- [ ] **Step 3: 修改 loadBooks 函数，添加「开始分析」按钮**

在 `loadBooks` 函数的 book card 渲染部分，添加开始分析按钮：

```javascript
bookCards.innerHTML = books.map((book) => {
  const isActive = String(book.id) === String(bookId);
  const indexed = Boolean(book.indexed);
  const status = book.status || "pending";
  const sourceTag = book.source === "upload"
    ? '<span class="source-tag upload">本地上传</span>'
    : '<span class="source-tag local">原书</span>';

  const actionBtn = status === "pending"
    ? `<button class="start-index-btn secondary" data-book-id="${escapeHtml(book.id)}">开始分析</button>`
    : status === "indexing"
    ? `<span class="status-tag">分析中...</span>`
    : status === "error"
    ? `<span class="status-tag error">分析失败</span>`
    : `<span class="status-tag ready">已就绪</span>`;

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
      <div class="book-meta">${actionBtn}</div>
      <div class="book-meta">ID：${escapeHtml(book.id)}</div>
    </div>
  `;
}).join("");
```

- [ ] **Step 4: 添加开始分析按钮事件**

在 `bindEvents` 函数中添加：

```javascript
// 开始分析按钮
document.addEventListener("click", (e) => {
  if (e.target.classList.contains("start-index-btn")) {
    const btn = e.target;
    const bookId = btn.dataset.bookId;
    startBookIndex(bookId);
  }
});

async function startBookIndex(bookId) {
  const btn = document.querySelector(`.start-index-btn[data-book-id="${bookId}"]`);
  if (btn) {
    btn.disabled = true;
    btn.textContent = "启动中...";
  }
  try {
    const result = await fetchJson(`/api/books/${bookId}/start-index`, { method: "POST" });
    if (result.status === "indexing") {
      navigateTo(`#/book/${bookId}`);
    }
  } catch (error) {
    handleActionError(error, "#book-cards", "启动失败");
  }
}
```

- [ ] **Step 5: 修改 bootstrap 调用 initRouter**

```javascript
async function bootstrap() {
  setTabs();
  setupGraphCanvas();
  bindEvents();
  syncGraphScopeToAsk();
  initRouter();  // 添加路由初始化
  // ... rest
}
```

- [ ] **Step 6: 提交**

```bash
git add static/app.js && git commit -m "feat: add hash-based routing for book detail page"
```

---

## Task 6: 详情页模板和样式

**Files:**
- Modify: `templates/dashboard.html`
- Modify: `static/styles.css`

- [ ] **Step 1: 添加详情页 HTML 容器**

在 `</div><!-- app-shell -->` 之前添加：

```html
<div id="book-detail-view" class="book-detail-view" hidden>
  <div class="detail-header">
    <button id="back-to-library" class="secondary">← 返回藏书</button>
    <h2 id="detail-book-title">《》</h2>
    <span id="detail-book-status" class="status-tag">等待分析</span>
  </div>
  <div class="detail-progress" id="detail-progress" hidden>
    <div class="progress-bar">
      <div class="progress-fill" id="progress-fill" style="width: 0%"></div>
    </div>
    <p id="progress-message">正在分析...</p>
  </div>
  <div class="detail-content" id="detail-content" hidden>
    <div class="detail-sidebar">
      <h3>人物卡片</h3>
      <div id="detail-character-cards" class="character-list"></div>
    </div>
    <div class="detail-main">
      <div class="graph-toolbar">
        <div class="graph-control">
          <label for="detail-graph-scope-start">章节范围</label>
          <div class="inline-fields compact">
            <input id="detail-graph-scope-start" type="number" value="1" min="1" />
            <span>至</span>
            <input id="detail-graph-scope-end" type="number" value="14" min="1" />
          </div>
        </div>
        <button id="detail-refresh-graph" class="secondary">刷新图谱</button>
      </div>
      <div class="graph-stage">
        <canvas id="detail-knowledge-graph-canvas"></canvas>
      </div>
    </div>
    <div class="detail-sidebar-right">
      <h3>事件时间线</h3>
      <div id="detail-timeline" class="timeline-board"></div>
    </div>
  </div>
</div>
```

- [ ] **Step 2: 添加详情页 CSS 样式**

在 `static/styles.css` 末尾添加：

```css
/* 详情页 */
.book-detail-view {
  display: grid;
  gap: 16px;
}

.detail-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  background: var(--panel);
  border-radius: var(--radius-lg);
}

.detail-header h2 {
  flex: 1;
}

.detail-progress {
  padding: 20px;
  background: var(--panel);
  border-radius: var(--radius-lg);
}

.progress-bar {
  height: 8px;
  background: var(--surface-strong);
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--accent), var(--accent-warm));
  transition: width 0.3s ease;
}

.detail-content {
  display: grid;
  grid-template-columns: 250px minmax(0, 1fr) 280px;
  gap: 16px;
}

.detail-sidebar,
.detail-sidebar-right {
  padding: 16px;
  background: var(--panel);
  border-radius: var(--radius-lg);
  max-height: 600px;
  overflow: auto;
}

.detail-main {
  display: grid;
  gap: 16px;
}
```

- [ ] **Step 3: 提交**

```bash
git add templates/dashboard.html static/styles.css && git commit -m "feat: add book detail page HTML and CSS"
```

---

## Task 7: 详情页交互逻辑

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: 实现 showBookDetail 函数**

```javascript
let detailGraphState = {
  canvas: null,
  ctx: null,
  nodes: [],
  edges: [],
  nodeMap: new Map(),
  selectedId: null,
  animationFrame: null,
  dpr: window.devicePixelRatio || 1,
};

async function showBookDetail(bookId) {
  $("#book-detail-view").hidden = false;
  $(".tab-bar").hidden = true;

  // 设置标题和状态
  const books = await fetchJson("/api/books");
  const book = books.find(b => b.id === bookId);
  if (book) {
    $("#detail-book-title").textContent = `《${book.title}》`;
    updateDetailStatus(book.status || "pending", 0);
  }

  // 如果已就绪，加载图谱
  if (book && book.status === "ready") {
    $("#detail-progress").hidden = true;
    $("#detail-content").hidden = false;
    await loadDetailGraph(bookId);
  } else if (book && book.status === "indexing") {
    // 轮询状态
    startPollingStatus(bookId);
  } else {
    $("#detail-progress").hidden = true;
    $("#detail-content").hidden = true;
  }

  // 返回按钮
  $("#back-to-library").onclick = () => navigateTo("#/");
}

function updateDetailStatus(status, progress) {
  const statusEl = $("#detail-book-status");
  const progressEl = $("#detail-progress");
  const fillEl = $("#progress-fill");
  const msgEl = $("#progress-message");

  statusEl.textContent = {
    pending: "等待分析",
    indexing: "分析中",
    ready: "已就绪",
    error: "分析失败"
  }[status] || status;

  if (status === "indexing") {
    progressEl.hidden = false;
    fillEl.style.width = `${(progress * 100).toFixed(0)}%`;
    msgEl.textContent = `正在分析... (${(progress * 100).toFixed(0)}%)`;
  } else if (status === "ready") {
    progressEl.hidden = true;
  }
}

function startPollingStatus(bookId) {
  const poll = async () => {
    const status = await fetchJson(`/api/books/${bookId}/status`);
    updateDetailStatus(status.status, status.progress);

    if (status.status === "indexing") {
      setTimeout(poll, 2000);
    } else if (status.status === "ready") {
      $("#detail-progress").hidden = true;
      $("#detail-content").hidden = false;
      await loadDetailGraph(bookId);
    }
  };
  poll();
}

async function loadDetailGraph(bookId) {
  // 复用现有图谱加载逻辑
  // ...
}
```

- [ ] **Step 2: 实现 showLibraryView 函数**

```javascript
function showLibraryView() {
  $("#book-detail-view").hidden = true;
  $(".tab-bar").hidden = false;
  stopPollingStatus();
}

function stopPollingStatus() {
  // 清理轮询状态
}
```

- [ ] **Step 3: 添加详情页图谱刷新按钮事件**

在 bindEvents 中添加：

```javascript
$("#detail-refresh-graph")?.addEventListener("click", () => {
  if (router.currentBookId) {
    loadDetailGraph(router.currentBookId);
  }
});
```

- [ ] **Step 4: 提交**

```bash
git add static/app.js && git commit -m "feat: implement book detail page interactions"
```

---

## Task 8: 集成测试

- [ ] **Step 1: 启动服务器**

```bash
cd D:\projects\小王一号 && python -m scripts.run_api
```

- [ ] **Step 2: 测试 API 端点**

```bash
# 获取书籍状态
curl http://localhost:8000/api/books/fanren-1-500/status

# 开始索引
curl -X POST http://localhost:8000/api/books/fanren-1-500/start-index
```

- [ ] **Step 3: 浏览器测试**

1. 打开 http://localhost:8000/
2. 上传一本新书
3. 点击「开始分析」
4. 验证跳转到详情页
5. 验证进度显示
6. 验证图谱加载

---

## 验收标准

1. ✅ 上传新书后显示「开始分析」按钮
2. ✅ 点击「开始分析」跳转到详情页 URL (#/book/{id})
3. ✅ 详情页显示书籍状态和进度
4. ✅ 返回按钮可回到藏书列表
5. ✅ 索引完成后显示图谱
6. ✅ 进度更新通过轮询实现

---

**Plan complete.** 建议使用 **Subagent-Driven** 方式执行。
