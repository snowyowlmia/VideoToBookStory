from pathlib import Path

from videotobookstory.web import _build_pdf_from_storybook


def test_build_pdf_from_storybook(tmp_path: Path):
    storybook = {
        "title": "测试绘本",
        "pages": [
            {"page_no": 1, "text": "故事开始啦"},
            {"page_no": 2, "text": "后来他们继续前进"},
        ],
    }
    storybook_json = tmp_path / "storybook.json"
    storybook_json.write_text(__import__("json").dumps(storybook, ensure_ascii=False), encoding="utf-8")

    output_pdf = tmp_path / "storybook.pdf"
    _build_pdf_from_storybook(storybook_json, output_pdf)

    assert output_pdf.exists()
    data = output_pdf.read_bytes()
    assert data.startswith(b"%PDF")
