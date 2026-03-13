# VideoToBookStory (MVP)

Local-first MVP with **CLI + Web UI**.

## What it does now
- Supports local video input (`--video`) and YouTube input (`--youtube-url`, via `yt-dlp`).
- Web UI supports paste YouTube link OR upload local video.
- Supports age-group style presets (`3-4`, `5-6`, `7-8`).
- Supports multi-language output (`--languages zh en`, checkbox multi-select in web).
- Supports **scene-based frame extraction** (default) to preserve transitions better than fixed-interval sampling.
- Adds first-pass continuity controls for 5-year-old Chinese style:
  - consistent main character naming,
  - supporting-character rotation,
  - coherent transition phrases.

## Requirements
- Python 3.10+
- `ffmpeg` and `ffprobe`
- `yt-dlp` (only required for YouTube input)

## Install
```bash
pip install -e . --no-build-isolation
```

## CLI usage

### A) Local video (scene split)
```bash
videotobookstory \
  --video /path/to/movie.mp4 \
  --title "给女儿的哈利波特" \
  --age-group 5-6 \
  --languages zh \
  --frame-strategy scene \
  --scene-threshold 0.35 \
  --main-character 哈利 \
  --supporting-characters 赫敏,罗恩 \
  --max-pages 24 \
  --output-dir ./output_harry
```

### B) YouTube test link
```bash
videotobookstory \
  --youtube-url "https://www.youtube.com/watch?v=P7S_8BrFMW4" \
  --title "给女儿的哈利波特" \
  --age-group 5-6 \
  --languages zh en \
  --frame-strategy scene \
  --scene-threshold 0.3 \
  --main-character 哈利 \
  --supporting-characters 赫敏,罗恩 \
  --youtube-clip-seconds 180 \
  --max-pages 20 \
  --output-dir ./output_youtube_test
```

## Web usage
```bash
videotobookstory-web --host 0.0.0.0 --port 8000
```
Open `http://127.0.0.1:8000` and then:
1. Paste YouTube link **or** upload local video.
2. Choose age group.
3. Multi-select languages.
4. Keep frame strategy as **scene** (recommended).
5. Fill character names for continuity.
6. Click **Convert** and download ZIP / PDF / Markdown links from the result panel.

### If you see `ERR_CONNECTION_REFUSED`
1. Keep the terminal running after launch (do not close it).
2. Confirm installation and launch again:
   ```bash
   pip install -e . --no-build-isolation
   python -m videotobookstory.web --host 0.0.0.0 --port 8000
   ```
3. Check service health from another terminal:
   ```bash
   curl http://127.0.0.1:8000/health
   ```
4. If using Docker/remote/container, expose/forward port `8000`.
5. If port `8000` is occupied, change to another port (example `8010`).

## Next implementation steps
1. Add subtitle/ASR grounding so text is tied to actual scene content.
2. Add stronger character/entity continuity checks across adjacent pages.
3. Add persistent local output folders from web UI (instead of temporary directory).
4. Improve PDF layout with images and better typography.
