import json


def test_prepare_chapters_reads_gb18030_source(test_repo, test_config, tmp_path):
    source = tmp_path / "zhuxian.txt"
    source.write_bytes(
        "第一章 青云\n张小凡站在青云山下。\n第二章 入门\n他拜入青云门。\n".encode("gb18030")
    )

    test_repo.ensure_book_manifest("zhuxian", "诛仙", str(source), source="upload")

    chapters = test_repo.prepare_chapters("zhuxian", str(source))

    assert [chapter["title"] for chapter in chapters] == ["青云", "入门"]
    assert chapters[0]["text"] == "张小凡站在青云山下。"
    manifest = json.loads((test_config.books_dir / "zhuxian" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["chapter_count"] == 2
