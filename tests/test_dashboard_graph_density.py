from pathlib import Path


def test_dashboard_requests_graph_density_auto():
    app_js = Path("static/app.js").read_text(encoding="utf-8")
    dashboard = Path("templates/dashboard.html").read_text(encoding="utf-8")

    assert "graph-density" in dashboard
    assert "detail-graph-density" in dashboard
    assert "currentGraphDensity" in app_js
    assert "density: currentGraphDensity()" in app_js
    assert 'limit: "20"' not in app_js


def test_dashboard_density_select_has_options():
    dashboard = Path("templates/dashboard.html").read_text(encoding="utf-8")

    # Check that both density selects have auto/compact/expanded options
    assert '<option value="auto" selected>自动</option>' in dashboard
    assert '<option value="compact">紧凑</option>' in dashboard
    assert '<option value="expanded">展开</option>' in dashboard


def test_detail_graph_sends_density():
    app_js = Path("static/app.js").read_text(encoding="utf-8")

    assert "currentDetailGraphDensity" in app_js
    assert "density=${encodeURIComponent(density)}" in app_js


def test_stats_line_shows_candidate_counts():
    app_js = Path("static/app.js").read_text(encoding="utf-8")

    assert "candidate_character_count" in app_js
    assert "candidate_event_count" in app_js


def test_large_graph_label_helper_exists():
    app_js = Path("static/app.js").read_text(encoding="utf-8")

    assert "function shouldDrawGraphLabel" in app_js
    assert "graphState.nodes.length" in app_js
    assert "function shouldDrawDetailGraphLabel" in app_js
    assert "detailGraphState.nodes.length" in app_js
