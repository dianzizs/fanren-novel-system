from pathlib import Path

from fastapi.testclient import TestClient

from novel_system.api import app


def test_ready_books_expose_analysis_detail_entrypoint():
    library_js = Path("static/js/library.js").read_text(encoding="utf-8")

    assert "open-book-btn" in library_js
    assert 'status === "ready"' in library_js
    assert "查看分析" in library_js
    assert 'appState.navigate(`#/book/${e.target.dataset.bookId}`)' in library_js


def test_detail_index_progress_renders_live_status_message():
    main_js = Path("static/js/main.js").read_text(encoding="utf-8")

    assert "function updateDetailStatus(status, progress, message = null)" in main_js
    assert 'msgEl.textContent = message || `正在分析... (${(progress * 100).toFixed(0)}%)`' in main_js
    assert "updateDetailStatus(status.status, status.progress, status.message)" in main_js


def test_dashboard_module_script_served_as_javascript():
    client = TestClient(app)

    response = client.get("/static/js/main.js?v=2")

    assert response.status_code == 200
    assert response.headers["content-type"].split(";")[0] == "application/javascript"


def test_window_lifecycle_endpoints_default_to_disabled():
    client = TestClient(app)
    original = app.state.config.shutdown_on_window_close
    app.state.config.shutdown_on_window_close = False

    try:
        heartbeat = client.post("/api/system/window-heartbeat")
        closed = client.post("/api/system/window-closed")
    finally:
        app.state.config.shutdown_on_window_close = original

    assert heartbeat.status_code == 200
    assert heartbeat.json() == {"enabled": False}
    assert closed.status_code == 200
    assert closed.json() == {"enabled": False}


def test_dashboard_sends_window_lifecycle_signals():
    main_js = Path("static/js/main.js").read_text(encoding="utf-8")

    assert "function initWindowLifecycleShutdown()" in main_js
    assert 'fetch("/api/system/window-heartbeat", { method: "POST", keepalive: true })' in main_js
    assert 'navigator.sendBeacon("/api/system/window-closed")' in main_js
    assert 'window.addEventListener("pagehide", sendWindowClosed)' in main_js
