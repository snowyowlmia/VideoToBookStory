from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

AGE_STYLES = {
    "3-4": {
        "voice": "超简短、口语、重复关键词",
        "templates": [
            "{transition}，{main_character}和大家还在往前走。",
            "你看，他们发现了一点点新线索。",
            "故事继续，我们一页一页看下去。",
        ],
    },
    "5-6": {
        "voice": "口语化、短句、因果清楚、连贯转场",
        "templates": [
            "{transition}，{main_character}发现了和目标有关的新线索。",
            "为了不让线索断掉，{main_character}和{partner}马上继续行动。",
            "他们把刚刚发生的事连起来看，终于更接近答案了。",
        ],
    },
    "7-8": {
        "voice": "口语化、稍完整叙述",
        "templates": [
            "{transition}，{main_character}遇到新的挑战，也更接近答案。",
            "这一步推动了主线，{main_character}做出了关键选择。",
            "下一段会进入明显转折，悬念继续增加。",
        ],
    },
}

SUPPORTED_LANGUAGES = ("zh", "en")
SUPPORTED_FRAME_STRATEGIES = ("scene", "interval")


@dataclass
class Page:
    page_no: int
    timestamp_s: float
    image_path: str
    text: str
    transition: str


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, text=True, capture_output=True)


def ensure_binary(name: str, install_tip: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"Missing dependency: {name}. {install_tip}")


def ensure_ffmpeg() -> None:
    ensure_binary("ffmpeg", "Please install FFmpeg and ensure it is in PATH.")
    ensure_binary("ffprobe", "Please install FFmpeg and ensure ffprobe is in PATH.")


def probe_duration(video_path: Path) -> float:
    result = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
    )
    return float(result.stdout.strip())


def download_youtube_video(url: str, work_dir: Path, clip_seconds: int | None) -> Path:
    ensure_binary("yt-dlp", "Install yt-dlp to enable YouTube input.")
    output = work_dir / "youtube_input.mp4"
    cmd = [
        "yt-dlp",
        "-f",
        "mp4/bestvideo+bestaudio/best",
        "--merge-output-format",
        "mp4",
        "-o",
        str(output),
    ]
    if clip_seconds and clip_seconds > 0:
        cmd.extend(["--download-sections", f"*0-{clip_seconds}"])
    cmd.append(url)
    _run(cmd)
    if not output.exists():
        found = sorted(work_dir.glob("youtube_input*"))
        if not found:
            raise RuntimeError("yt-dlp did not produce a local video file.")
        return found[0]
    return output


def extract_interval_frames(video_path: Path, output_dir: Path, interval_s: int) -> list[Path]:
    frames_dir = output_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    pattern = frames_dir / "frame_%04d.jpg"
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vf",
            f"fps=1/{interval_s}",
            "-q:v",
            "3",
            str(pattern),
        ]
    )
    return sorted(frames_dir.glob("frame_*.jpg"))


def extract_scene_frames(video_path: Path, output_dir: Path, threshold: float) -> list[Path]:
    frames_dir = output_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    pattern = frames_dir / "scene_%04d.jpg"
    expr = f"select='eq(n,0)+gt(scene,{threshold})'"
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vf",
            expr,
            "-vsync",
            "vfr",
            "-q:v",
            "3",
            str(pattern),
        ]
    )
    return sorted(frames_dir.glob("scene_*.jpg"))


def _partner_for_page(page_no: int, supporting_characters: list[str]) -> str:
    if not supporting_characters:
        return "伙伴"
    return supporting_characters[(page_no - 1) % len(supporting_characters)]


def build_pages(
    frames: list[Path],
    duration_s: float,
    title: str,
    age_group: str,
    language: str,
    main_character: str,
    supporting_characters: list[str],
) -> list[Page]:
    transitions_zh = ["先是", "接着", "后来", "不久之后", "就在这时", "最后"]
    transitions_en = ["First", "Next", "Later", "Soon", "Just then", "Finally"]
    transitions = transitions_zh if language == "zh" else transitions_en

    templates = AGE_STYLES[age_group]["templates"]
    pages: list[Page] = []
    total = len(frames)

    for i, frame in enumerate(frames, start=1):
        ts = (i - 1) * (duration_s / max(total, 1))
        transition = transitions[min(i - 1, len(transitions) - 1)] if i <= len(transitions) else transitions[(i - 1) % len(transitions)]
        partner = _partner_for_page(i, supporting_characters)

        if language == "zh":
            if i == 1:
                text = f"故事开始啦！{main_character}正在观察周围，想搞清楚发生了什么。"
            elif i == total:
                text = f"最后，{main_character}把前面的线索都连了起来，这一段冒险先告一段落。"
            else:
                template = templates[(i - 2) % len(templates)]
                text = template.format(
                    transition=transition,
                    title=title,
                    main_character=main_character,
                    partner=partner,
                )
        else:
            if i == 1:
                text = f"The story begins. {main_character} looks around and tries to understand what is happening."
            elif i == total:
                text = f"Finally, {main_character} connects earlier clues, and this part of the adventure wraps up."
            else:
                text = f"{transition}, {main_character} keeps moving the story forward with {partner}."

        pages.append(
            Page(
                page_no=i,
                timestamp_s=round(ts, 2),
                image_path=str(frame),
                text=text,
                transition=transition,
            )
        )
    return pages


def write_outputs(
    output_dir: Path,
    title: str,
    pages: list[Page],
    duration_s: float,
    age_group: str,
    language: str,
    main_character: str,
    supporting_characters: list[str],
) -> None:
    manifest = {
        "title": title,
        "duration_s": duration_s,
        "total_pages": len(pages),
        "age_group": age_group,
        "language": language,
        "main_character": main_character,
        "supporting_characters": supporting_characters,
        "pages": [asdict(p) for p in pages],
    }
    (output_dir / "storybook.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md_lines = [f"# {title} Picture Book", ""]
    for p in pages:
        rel = Path(p.image_path).relative_to(output_dir)
        md_lines.append(f"## Page {p.page_no}")
        md_lines.append(f"![page {p.page_no}]({rel.as_posix()})")
        md_lines.append(p.text)
        md_lines.append(f"*转场/Transition: {p.transition}*")
        md_lines.append("")
    (output_dir / "storybook.md").write_text("\n".join(md_lines), encoding="utf-8")


def _normalize_characters(raw_characters: str) -> list[str]:
    return [c.strip() for c in raw_characters.split(",") if c.strip()]


def convert_to_storybook(
    *,
    output_dir: Path,
    title: str,
    age_group: str,
    languages: list[str],
    interval_seconds: int,
    max_pages: int,
    youtube_clip_seconds: int,
    frame_strategy: str,
    scene_threshold: float,
    main_character: str,
    supporting_characters: list[str],
    video_path: Path | None = None,
    youtube_url: str | None = None,
) -> dict[str, Path]:
    ensure_ffmpeg()
    output_dir.mkdir(parents=True, exist_ok=True)

    if video_path is None and not youtube_url:
        raise ValueError("Either video_path or youtube_url must be provided.")

    source_path = video_path
    if youtube_url:
        source_path = download_youtube_video(youtube_url, output_dir, youtube_clip_seconds)
    if source_path is None or not source_path.exists():
        raise FileNotFoundError(f"Video not found: {source_path}")

    duration = probe_duration(source_path)
    if frame_strategy == "scene":
        raw_frames = extract_scene_frames(source_path, output_dir, scene_threshold)
    else:
        raw_frames = extract_interval_frames(source_path, output_dir, interval_seconds)

    if not raw_frames:
        raise RuntimeError("No frames extracted. Try a different strategy or lower scene threshold.")

    limit = max(1, max_pages)
    if len(raw_frames) > limit:
        step = len(raw_frames) / limit
        sampled = [raw_frames[min(math.floor(i * step), len(raw_frames) - 1)] for i in range(limit)]
    else:
        sampled = raw_frames

    outputs: dict[str, Path] = {}
    for lang in languages:
        if lang not in SUPPORTED_LANGUAGES:
            continue
        lang_dir = output_dir / f"book_{lang}"
        lang_dir.mkdir(parents=True, exist_ok=True)
        pages = build_pages(
            frames=sampled,
            duration_s=duration,
            title=title,
            age_group=age_group,
            language=lang,
            main_character=main_character,
            supporting_characters=supporting_characters,
        )
        write_outputs(
            output_dir=lang_dir,
            title=title,
            pages=pages,
            duration_s=duration,
            age_group=age_group,
            language=lang,
            main_character=main_character,
            supporting_characters=supporting_characters,
        )
        outputs[lang] = lang_dir

    if not outputs:
        raise ValueError("No valid language selected. Use one or more of: zh, en")

    return outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a local picture-book draft from a video file or YouTube URL."
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--video", type=Path, help="Path to local video file")
    source_group.add_argument("--youtube-url", help="YouTube URL to download and process")
    parser.add_argument("--title", default="My Story Book", help="Book title")
    parser.add_argument("--age-group", choices=sorted(AGE_STYLES.keys()), default="5-6")
    parser.add_argument(
        "--languages",
        nargs="+",
        choices=list(SUPPORTED_LANGUAGES),
        default=["zh"],
        help="One or more output languages (default: zh)",
    )
    parser.add_argument("--frame-strategy", choices=list(SUPPORTED_FRAME_STRATEGIES), default="scene")
    parser.add_argument("--scene-threshold", type=float, default=0.35)
    parser.add_argument("--interval-seconds", type=int, default=20)
    parser.add_argument("--max-pages", type=int, default=40)
    parser.add_argument("--youtube-clip-seconds", type=int, default=180)
    parser.add_argument("--main-character", default="小主人公")
    parser.add_argument(
        "--supporting-characters",
        default="朋友",
        help="Comma-separated names, e.g. '赫敏,罗恩'",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    return parser.parse_args()


def run() -> None:
    args = parse_args()
    outputs = convert_to_storybook(
        output_dir=args.output_dir,
        title=args.title,
        age_group=args.age_group,
        languages=args.languages,
        interval_seconds=args.interval_seconds,
        max_pages=args.max_pages,
        youtube_clip_seconds=args.youtube_clip_seconds,
        frame_strategy=args.frame_strategy,
        scene_threshold=args.scene_threshold,
        main_character=args.main_character,
        supporting_characters=_normalize_characters(args.supporting_characters),
        video_path=args.video,
        youtube_url=args.youtube_url,
    )
    for lang, out in outputs.items():
        print(f"[{lang}] Done: {out}")


if __name__ == "__main__":
    run()
