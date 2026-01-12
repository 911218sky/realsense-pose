import argparse
import gzip
import mimetypes
from io import BytesIO
from pathlib import Path


def _gzip_bytes(data: bytes, level: int = 6) -> bytes:
    # Generate gzip compression result (fixed mtime=0 for consistent .gz bytes across builds, useful for caching/comparison)
    buf = BytesIO()
    with gzip.GzipFile(filename="", mode="wb", compresslevel=level, mtime=0, fileobj=buf) as f:
        f.write(data)
    return buf.getvalue()


def _should_compress(path: Path) -> bool:
    """Determine if a file should have .br / .gz precompressed versions."""
    if not path.is_file():
        return False
    if path.suffix in {".br", ".gz"}:
        # Already a compressed file, don't double-compress
        return False

    # Skip already highly compressed or poorly compressible formats (compression won't save much, just wastes time/space)
    if path.suffix.lower() in {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".zip",
        ".7z",
        ".gz",
        ".br",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".mp3",
        ".mp4",
    }:
        return False

    rel = path.as_posix()
    name = path.name

    # Flutter Web common large entry files, always compress
    if name in {"main.dart.js", "flutter_bootstrap.js", "flutter.js"}:
        return True

    # CanvasKit / skwasm usually large, high compression benefit
    if "/canvaskit/" in rel:
        return True

    # Common static files: text or compressible binary (including .wasm)
    # - Compressed versions will be created in same directory: <original_name>.br and <original_name>.gz
    if path.suffix.lower() in {".js", ".wasm", ".symbols", ".css", ".html", ".json", ".map", ".svg"}:
        return True

    # If MIME type looks compressible, allow it too (conservative fallback)
    mime, _ = mimetypes.guess_type(str(path))
    if mime and (mime.startswith("text/") or mime in {"application/javascript", "application/json", "application/wasm"}):
        return True

    return False


def _is_up_to_date(src: Path, dst: Path) -> bool:
    """Check if target compressed file exists and is newer than source (avoid recompressing every time)."""
    if not dst.exists():
        return False
    try:
        return dst.stat().st_mtime >= src.stat().st_mtime and dst.stat().st_size > 0
    except OSError:
        return False


def main() -> int:
    try:
        import brotli
    except ModuleNotFoundError as e:
        raise SystemExit(
            "Missing dependency 'brotli'. Install it with: pip install brotli\n"
            "In Docker builds, this is installed via requirements_db.txt."
        ) from e

    # Purpose: precompress Flutter Web build output files so server can directly return .br/.gz (faster, less bandwidth)
    parser = argparse.ArgumentParser(description="Precompress Flutter Web assets to .br and .gz")
    parser.add_argument("--web-dir", required=True, help="Path to Flutter web build output (e.g. ./web)")
    parser.add_argument("--br-quality", type=int, default=8, help="Brotli quality (0-11). Default 11.")
    parser.add_argument("--gzip-level", type=int, default=6, help="Gzip level (0-9). Default 9.")
    parser.add_argument("--min-bytes", type=int, default=1024, help="Only compress files >= this size. Default 1024.")
    # --force: rebuild .br/.gz even if they exist and are newer than source (e.g., if you changed compression quality/level)
    parser.add_argument("--force", action="store_true", help="Rebuild even if .br/.gz exist and are newer than source.")
    args = parser.parse_args()

    web_dir = Path(args.web_dir).resolve()
    if not web_dir.exists() or not web_dir.is_dir():
        raise SystemExit(f"web dir not found: {web_dir}")

    total = 0
    br_built = 0
    gz_built = 0

    for p in web_dir.rglob("*"):
        if not _should_compress(p):
            continue

        try:
            size = p.stat().st_size
        except OSError:
            continue
        if size < args.min_bytes:
            # File too small, compression benefit minimal, skip
            continue

        total += 1
        br_path = p.with_name(p.name + ".br")
        gz_path = p.with_name(p.name + ".gz")

        if not args.force and _is_up_to_date(p, br_path) and _is_up_to_date(p, gz_path):
            # Already have latest compressed files, skip
            continue

        data = p.read_bytes()

        # Brotli
        br_data = brotli.compress(data, quality=args.br_quality)
        br_path.write_bytes(br_data)
        br_built += 1

        # Gzip
        gz_data = _gzip_bytes(data, level=args.gzip_level)
        gz_path.write_bytes(gz_data)
        gz_built += 1

    print(f"[precompress_web] web_dir={web_dir}")
    print(f"[precompress_web] candidates={total} br_built={br_built} gz_built={gz_built}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())