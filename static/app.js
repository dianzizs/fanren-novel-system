const bookId = document.body.dataset.bookId;
let currentChapter = 1;

const $ = (selector) => document.querySelector(selector);

function setTabs() {
  document.querySelectorAll(".tab").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      document.querySelector(`#tab-${button.dataset.tab}`).classList.add("active");
    });
  });
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

async function loadBooks() {
  const books = await fetchJson("/api/books");
  $("#book-cards").innerHTML = books.map((book) => `
    <div class="book-card">
      <div class="status-tag">${book.indexed ? "已索引" : "待索引"}</div>
      <h3>${book.title}</h3>
      <div class="book-meta">ID: ${book.id}</div>
      <div class="book-meta">章节数: ${book.chapter_count || "-"}</div>
      <div class="book-meta">Chunk 数: ${book.chunk_count || "-"}</div>
      <div class="book-meta">${book.source_path}</div>
    </div>
  `).join("");
}

async function loadReader(chapter = 1) {
  const payload = await fetchJson(`/api/books/${bookId}/reader?chapter=${chapter}`);
  currentChapter = payload.current_chapter.chapter;
  $("#reader-summary").innerHTML = `
    <h3>第${payload.current_chapter.chapter}章 ${payload.current_chapter.title}</h3>
    <p>${payload.chapters.find((item) => item.chapter === payload.current_chapter.chapter)?.summary || ""}</p>
  `;
  $("#reader-content").textContent = payload.current_chapter.text;
  $("#chapter-tree").innerHTML = payload.chapters.map((chapterItem) => `
    <div class="chapter-item ${chapterItem.chapter === currentChapter ? "active" : ""}" data-chapter="${chapterItem.chapter}">
      <strong>第${chapterItem.chapter}章</strong><br />
      <span>${chapterItem.title}</span>
    </div>
  `).join("");
  $("#character-cards").innerHTML = payload.top_characters.map((character) => `
    <div class="character-card">
      <strong>${character.title}</strong>
      <p>${character.text}</p>
    </div>
  `).join("");
  $("#timeline-board").innerHTML = payload.timeline.map((event) => `
    <div class="timeline-card">
      <strong>第${event.chapter}章 ${event.title}</strong>
      <p>${event.description}</p>
    </div>
  `).join("");
  document.querySelectorAll(".chapter-item").forEach((item) => {
    item.addEventListener("click", () => loadReader(item.dataset.chapter));
  });
}

async function askQuestion() {
  const scopeStart = Number($("#scope-start").value);
  const scopeEnd = Number($("#scope-end").value);
  const payload = {
    user_query: $("#ask-query").value.trim(),
    scope: { chapters: [scopeStart, scopeEnd] },
    conversation_history: [
      { role: "user", content: "之后回答都尽量简短一点，但要带证据。" },
    ],
    session_id: "workspace",
  };
  const result = await fetchJson(`/api/books/${bookId}/ask`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  $("#ask-result").innerHTML = `
    <h3>回答</h3>
    <p>${result.answer.replace(/\n/g, "<br />")}</p>
    <div class="answer-meta">任务类型: ${result.planner.task_type} | 不确定性: ${result.uncertainty}</div>
  `;
  $("#evidence-list").innerHTML = result.evidence.map((item) => `
    <div class="evidence-card">
      <strong>第${item.chapter}章 · ${item.target}</strong>
      <p>${item.quote}</p>
      <div class="book-meta">${item.source}</div>
    </div>
  `).join("");
}

async function continueStory() {
  const scopeStart = Number($("#scope-start").value);
  const scopeEnd = Number($("#scope-end").value);
  const payload = {
    user_query: $("#continuation-query").value.trim(),
    scope: { chapters: [scopeStart, scopeEnd] },
    conversation_history: [
      { role: "user", content: "只看前14章，不要剧透后面。" },
    ],
    session_id: "workspace",
  };
  const result = await fetchJson(`/api/books/${bookId}/continue`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  $("#continuation-result").textContent = result.answer;
}

async function loadDashboard() {
  const dashboard = await fetchJson("/api/dashboard");
  $("#metric-grid").innerHTML = dashboard.metrics.map((item) => `
    <div class="metric-card">
      <strong>${item.name}</strong>
      <div class="metric-value">${item.value ?? "--"}</div>
      <div class="metric-note">${item.note ?? ""}</div>
    </div>
  `).join("");
  $("#baseline-list").innerHTML = dashboard.baseline_comparison.map((item) => `
    <div class="baseline-item">
      <strong>${item.system}</strong>
      <div>${item.score}</div>
    </div>
  `).join("") || "<div class='baseline-item'>尚未生成基线对比。</div>";
  $("#failure-list").innerHTML = dashboard.failures.map((item) => `
    <div class="failure-card">
      <strong>${item.id}</strong>
      <div>类别: ${item.category}</div>
      <div>得分: ${item.score}</div>
    </div>
  `).join("") || "<div class='failure-card'>暂无失败样例。</div>";
  $("#chart-json").textContent = JSON.stringify(dashboard.charts, null, 2);
}

async function rebuildIndex() {
  $("#index-book-btn").textContent = "索引中...";
  try {
    await fetchJson(`/api/books/${bookId}/index`, { method: "POST" });
    await loadBooks();
    await loadReader(currentChapter);
    await loadDashboard();
  } finally {
    $("#index-book-btn").textContent = "重建索引";
  }
}

function bindEvents() {
  $("#ask-btn").addEventListener("click", askQuestion);
  $("#continue-btn").addEventListener("click", continueStory);
  $("#reload-dashboard-btn").addEventListener("click", loadDashboard);
  $("#index-book-btn").addEventListener("click", rebuildIndex);
}

async function bootstrap() {
  setTabs();
  bindEvents();
  await loadBooks();
  await loadReader(1);
  await loadDashboard();
}

bootstrap().catch((error) => {
  console.error(error);
  $("#book-cards").innerHTML = `<div class="book-card">${error.message}</div>`;
});

