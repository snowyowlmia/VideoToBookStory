from pathlib import Path

from videotobookstory.main import build_pages


def test_build_pages_zh_continuity():
    frames = [Path(f"/tmp/f{i}.jpg") for i in range(1, 5)]
    pages = build_pages(
        frames=frames,
        duration_s=40,
        title="测试书",
        age_group="5-6",
        language="zh",
        main_character="哈利",
        supporting_characters=["赫敏", "罗恩"],
    )

    assert len(pages) == 4
    assert "哈利" in pages[0].text
    assert pages[1].transition in {"接着", "先是", "后来", "不久之后", "就在这时", "最后"}
    assert any(name in pages[2].text for name in ["赫敏", "罗恩"])
    assert "最后" in pages[-1].text


def test_build_pages_en_exists():
    frames = [Path("/tmp/f1.jpg"), Path("/tmp/f2.jpg")]
    pages = build_pages(
        frames=frames,
        duration_s=12,
        title="Test",
        age_group="7-8",
        language="en",
        main_character="Harry",
        supporting_characters=["Hermione"],
    )

    assert pages[0].text.startswith("The story begins")
    assert "Finally" in pages[-1].text or "wraps up" in pages[-1].text
