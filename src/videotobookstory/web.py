from __future__ import annotations

import cgi
import html
import json
import shutil
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from videotobookstory.main import AGE_STYLES, SUPPORTED_LANGUAGES, convert_to_storybook

BASE_RUNS_DIR = Path.cwd() / ".web_runs"


def _pdf_hex(text: str) -> str:
    return "".join(f"{b:02X}" for b in text.encode("utf-16-be"))


def _write_simple_pdf(lines: list[str], output_pdf: Path) -> None:
    content_lines = ["BT", "/F1 14 Tf", "50 800 Td"]
    for idx, line in enumerate(lines):
        if idx > 0:
            content_lines.append("0 -20 Td")
        content_lines.append(f"<{_pdf_hex(line)}> Tj")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("ascii")

    objects = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objects.append(
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
    )
    objects.append(
        b"<< /Type /Font /Subtype /Type0 /BaseFont /STSong-Light /Encoding /UniGB-UCS2-H /DescendantFonts [6 0 R] >>"
    )
    objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream")
    objects.append(
        b"<< /Type /Font /Subtype /CIDFontType0 /BaseFont /STSong-Light /CIDSystemInfo << /Registry (Adobe) /Ordering (GB1) /Supplement 4 >> >>"
    )

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{i} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_start = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        pdf.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n".encode("ascii")
    )
    output_pdf.write_bytes(pdf)


def _build_pdf_from_storybook(storybook_json: Path, output_pdf: Path) -> None:
    data = json.loads(storybook_json.read_text(encoding="utf-8"))
    lines = [f"{data.get('title', 'Story Book')}"]
    for p in data.get("pages", []):
        lines.append(f"P{p['page_no']}: {p['text']}")
    _write_simple_pdf(lines[:35], output_pdf)


def _send_file(handler: BaseHTTPRequestHandler, file_path: Path, download_name: str, content_type: str) -> None:
    data = file_path.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Disposition", f"attachment; filename={download_name}")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


class AppHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/health"):
            self._send_html("ok")
            return

        if self.path.startswith("/download"):
            qs = parse_qs(urlparse(self.path).query)
            file_param = (qs.get("file") or [""])[0]
            if not file_param:
                self.send_error(400, "Missing file parameter")
                return
            target = (BASE_RUNS_DIR / file_param).resolve()
            if not str(target).startswith(str(BASE_RUNS_DIR.resolve())) or not target.exists():
                self.send_error(404, "File not found")
                return

            suffix = target.suffix.lower()
            content_type = "application/octet-stream"
            if suffix == ".zip":
                content_type = "application/zip"
            elif suffix == ".pdf":
                content_type = "application/pdf"
            elif suffix == ".md":
                content_type = "text/markdown; charset=utf-8"

            _send_file(self, target, target.name, content_type)
            return

        self._send_html(render_form())

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/convert":
            self.send_error(404)
            return

        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": self.headers.get("Content-Type", "")},
        )

        title = (form.getfirst("title") or "给女儿的故事书").strip()
        age_group = (form.getfirst("age_group") or "5-6").strip()
        youtube_url = (form.getfirst("youtube_url") or "").strip()
        interval_seconds = int(form.getfirst("interval_seconds") or "20")
        max_pages = int(form.getfirst("max_pages") or "40")
        clip_seconds = int(form.getfirst("youtube_clip_seconds") or "180")
        frame_strategy = (form.getfirst("frame_strategy") or "scene").strip()
        scene_threshold = float(form.getfirst("scene_threshold") or "0.35")
        main_character = (form.getfirst("main_character") or "小主人公").strip()
        supporting_characters = (form.getfirst("supporting_characters") or "朋友").strip()
        languages = form.getlist("languages") or ["zh"]

        uploaded_video = form["video"] if "video" in form else None

        run_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        run_dir = BASE_RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        local_video_path = None
        if uploaded_video is not None and getattr(uploaded_video, "filename", ""):
            raw = uploaded_video.file.read()
            filename = Path(uploaded_video.filename).name or "upload.mp4"
            local_video_path = run_dir / filename
            local_video_path.write_bytes(raw)

        try:
            outputs = convert_to_storybook(
                output_dir=run_dir,
                title=title,
                age_group=age_group,
                languages=languages,
                interval_seconds=interval_seconds,
                max_pages=max_pages,
                youtube_clip_seconds=clip_seconds,
                frame_strategy=frame_strategy,
                scene_threshold=scene_threshold,
                main_character=main_character,
                supporting_characters=[c.strip() for c in supporting_characters.split(",") if c.strip()],
                video_path=local_video_path,
                youtube_url=youtube_url or None,
            )

            # generate pdf per language (simple text PDF)
            pdf_links = []
            md_links = []
            for lang, path in outputs.items():
                story_json = path / "storybook.json"
                story_md = path / "storybook.md"
                story_pdf = path / "storybook.pdf"
                _build_pdf_from_storybook(story_json, story_pdf)

                md_rel = story_md.relative_to(BASE_RUNS_DIR).as_posix()
                pdf_rel = story_pdf.relative_to(BASE_RUNS_DIR).as_posix()
                md_links.append(f"<li>{lang} Markdown: <a href='/download?file={md_rel}'>下载 .md</a></li>")
                pdf_links.append(f"<li>{lang} PDF: <a href='/download?file={pdf_rel}'>下载 .pdf</a></li>")

            archive_base = run_dir / "storybook_bundle"
            zip_path = Path(shutil.make_archive(str(archive_base), "zip", root_dir=run_dir))
            zip_rel = zip_path.relative_to(BASE_RUNS_DIR).as_posix()

            message = (
                "<h3>转换完成 ✅</h3>"
                "<p>你现在可以直接下载 ZIP / PDF / Markdown。</p>"
                f"<p><a href='/download?file={zip_rel}'><strong>⬇ 下载全部 ZIP</strong></a></p>"
                "<ul>"
                + "".join(pdf_links)
                + "".join(md_links)
                + "</ul>"
            )
            self._send_html(render_form(message=message))
        except Exception as exc:  # pylint: disable=broad-except
            self._send_html(render_form(message=f"<p style='color:red'>转换失败: {html.escape(str(exc))}</p>"))

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _send_html(self, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def render_form(message: str = "") -> str:
    age_options = "".join(
        f"<option value='{k}' {'selected' if k == '5-6' else ''}>{k} ({v['voice']})</option>"
        for k, v in AGE_STYLES.items()
    )
    language_checks = "".join(
        f"<label><input type='checkbox' name='languages' value='{lang}' {'checked' if lang=='zh' else ''}/> {lang}</label>"
        for lang in SUPPORTED_LANGUAGES
    )
    return f"""
<!doctype html>
<html lang='zh'>
<head>
  <meta charset='utf-8' />
  <title>VideoToBookStory Web MVP</title>
  <style>
    body {{ font-family: sans-serif; margin: 2rem; max-width: 900px; }}
    .card {{ border: 1px solid #ddd; border-radius: 8px; padding: 1rem; margin-top: 1rem; }}
    label {{ display:block; margin:.5rem 0 .2rem; }}
    input, select {{ width: 100%; padding: .5rem; }}
    .inline > label {{ display:inline-block; margin-right: 1rem; }}
    button {{ margin-top: 1rem; padding: .6rem 1rem; }}
    small {{ color: #666; }}
  </style>
</head>
<body>
  <h1>VideoToBookStory（本地网页 MVP）</h1>
  <p>流程：Paste YouTube 或 Upload 本地视频 -> 选年龄/语言 -> Convert。</p>
  <div class='card'>
    <form action='/convert' method='post' enctype='multipart/form-data'>
      <label>绘本标题</label>
      <input name='title' value='给女儿的故事书' />

      <label>YouTube 链接（可选）</label>
      <input name='youtube_url' placeholder='https://www.youtube.com/watch?v=...' />

      <label>本地视频上传（可选）</label>
      <input type='file' name='video' accept='video/*' />

      <label>年龄段</label>
      <select name='age_group'>{age_options}</select>

      <label>语言（可多选）</label>
      <div class='inline'>{language_checks}</div>

      <label>抽帧策略</label>
      <select name='frame_strategy'>
        <option value='scene' selected>按镜头切分（推荐）</option>
        <option value='interval'>固定时间抽帧</option>
      </select>
      <small>镜头切分使用 FFmpeg scene 检测；如果镜头太少可降低阈值。</small>

      <label>镜头阈值（scene threshold）</label>
      <input type='number' step='0.05' name='scene_threshold' value='0.35' min='0.05' max='0.95' />

      <label>主角名字（人物一致性）</label>
      <input name='main_character' value='哈利' />

      <label>配角名字（逗号分隔）</label>
      <input name='supporting_characters' value='赫敏,罗恩' />

      <label>固定抽帧间隔（秒，仅 interval 模式使用）</label>
      <input type='number' name='interval_seconds' value='12' min='1' />

      <label>最大页数</label>
      <input type='number' name='max_pages' value='20' min='1' />

      <label>YouTube 测试下载秒数</label>
      <input type='number' name='youtube_clip_seconds' value='180' min='30' />

      <button type='submit'>Convert</button>
    </form>
  </div>
  <div class='card'>{message}</div>
</body>
</html>
"""


def run_web() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run VideoToBookStory web MVP")
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Bind host (default: 0.0.0.0 for local + container port forwarding)",
    )
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    BASE_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), AppHandler)
    print(f"Web MVP running at http://{args.host}:{args.port}")
    print("If browser shows ERR_CONNECTION_REFUSED, ensure this process is still running and that port forwarding/firewall allows access.")
    server.serve_forever()


if __name__ == "__main__":
    run_web()
