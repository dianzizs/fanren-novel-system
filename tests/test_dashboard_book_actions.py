from pathlib import Path

from fastapi.testclient import TestClient

from novel_system.api import app


def test_ready_books_expose_analysis_detail_entrypoint():
    library_js = Path("static/js/library.js").read_text(encoding="utf-8")

    assert "open-book-btn" in library_js
    assert 'status === "ready"' in library_js
    assert "查看分析" in library_js
    assert 'appState.navigate(`#/book/${e.target.dataset.bookId}`)' in library_js


def test_dashboard_module_script_served_as_javascript():
    client = TestClient(app)

    response = client.get("/static/js/main.js?v=2")

    assert response.status_code == 200
    assert response.headers["content-type"].split(";")[0] == "application/javascript"
