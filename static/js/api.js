/**
 * API 封装模块 — 所有 fetch 调用集中管理
 */

const DEFAULT_TIMEOUT = 30000;

export async function request(url, options = {}) {
  const controller = new AbortController();
  const timeout = options.timeout || DEFAULT_TIMEOUT;
  const timer = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(url, {
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      ...options,
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `HTTP ${response.status}`);
    }
    return response.json();
  } finally {
    clearTimeout(timer);
  }
}

export async function getBooks() {
  return request("/api/books");
}

export async function importBook(formData) {
  const response = await fetch("/api/books", { method: "POST", body: formData });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

export async function deleteBook(bookId) {
  return request(`/api/books/${encodeURIComponent(bookId)}`, { method: "DELETE" });
}

export async function indexBook(bookId, force = false) {
  const qs = force ? "?force=true" : "";
  return request(`/api/books/${encodeURIComponent(bookId)}/start-index${qs}`, { method: "POST" });
}

export async function getBookStatus(bookId) {
  return request(`/api/books/${encodeURIComponent(bookId)}/status`);
}

export async function getReaderPayload(bookId, chapter = 1) {
  return request(`/api/books/${encodeURIComponent(bookId)}/reader?chapter=${chapter}`);
}

export async function askQuestion(bookId, payload) {
  return request(`/api/books/${encodeURIComponent(bookId)}/ask`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function generateContinuation(bookId, payload) {
  return request(`/api/books/${encodeURIComponent(bookId)}/continue`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getGraphData(bookId, params) {
  const query = new URLSearchParams(params);
  return request(`/api/books/${encodeURIComponent(bookId)}/graph?${query.toString()}`);
}

export async function getDashboard() {
  return request("/api/dashboard");
}

export async function getStorageStats() {
  return request("/api/storage-stats");
}

export async function getTokenStats() {
  return request("/api/token-stats");
}

export async function getArtifacts(bookId) {
  return request(`/api/books/${encodeURIComponent(bookId)}/artifacts`);
}

export async function getArtifact(bookId, artifactName) {
  return request(`/api/books/${encodeURIComponent(bookId)}/artifacts/${artifactName}`);
}
