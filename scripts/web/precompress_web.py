import argparse
import gzip
import mimetypes
from io import BytesIO
from pathlib import Path


def _gzip_bytes(data: bytes, level: int = 6) -> bytes:
    # 產生 gzip 壓縮結果（固定 mtime=0，讓每次建置輸出的 .gz 位元組一致，便於快取/比對）
    buf = BytesIO()
    with gzip.GzipFile(filename="", mode="wb", compresslevel=level, mtime=0, fileobj=buf) as f:
        f.write(data)
    return buf.getvalue()


def _should_compress(path: Path) -> bool:
    """判斷某個檔案是否需要產出 .br / .gz 預壓縮檔。"""
    if not path.is_file():
        return False
    if path.suffix in {".br", ".gz"}:
        # 已經是壓縮檔本體，不再重複壓縮
        return False

    # 跳過已經高度壓縮或壓縮效果很差的格式（壓了也不會小多少，反而浪費時間/空間）
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

    # Flutter Web 常見的大型入口檔，固定要壓縮
    if name in {"main.dart.js", "flutter_bootstrap.js", "flutter.js"}:
        return True

    # CanvasKit / skwasm 通常很大，壓縮收益很高
    if "/canvaskit/" in rel:
        return True

    # 常見靜態檔：文字或可壓縮的二進位（包含 .wasm）
    # - 壓縮後會在同目錄產出：<原檔名>.br 與 <原檔名>.gz
    if path.suffix.lower() in {".js", ".wasm", ".symbols", ".css", ".html", ".json", ".map", ".svg"}:
        return True

    # 若 MIME 類型看起來可壓縮，也允許（保守補漏）
    mime, _ = mimetypes.guess_type(str(path))
    if mime and (mime.startswith("text/") or mime in {"application/javascript", "application/json", "application/wasm"}):
        return True

    return False


def _is_up_to_date(src: Path, dst: Path) -> bool:
    """目標壓縮檔是否已存在且比來源檔新（避免每次都重壓）。"""
    if not dst.exists():
        return False
    try:
        return dst.stat().st_mtime >= src.stat().st_mtime and dst.stat().st_size > 0
    except OSError:
        return False


def main() -> int:
    try:
        import brotli  # type: ignore
    except ModuleNotFoundError as e:
        raise SystemExit(
            "Missing dependency 'brotli'. Install it with: pip install brotli\n"
            "In Docker builds, this is installed via requirements_db.txt."
        ) from e

    # 目的：把 Flutter Web build 輸出的檔案預先壓縮，讓伺服器可以直接回傳 .br/.gz（更快、更省流量）
    parser = argparse.ArgumentParser(description="Precompress Flutter Web assets to .br and .gz")
    parser.add_argument("--web-dir", required=True, help="Path to Flutter web build output (e.g. ./web)")
    parser.add_argument("--br-quality", type=int, default=11, help="Brotli quality (0-11). Default 11.")
    parser.add_argument("--gzip-level", type=int, default=9, help="Gzip level (0-9). Default 9.")
    parser.add_argument("--min-bytes", type=int, default=1024, help="Only compress files >= this size. Default 1024.")
    # --force：即使 .br/.gz 已經存在且較新，也強制重建（例如你改了壓縮品質/等級想重做）
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
            # 檔案太小，壓縮收益不大，略過
            continue

        total += 1
        br_path = p.with_name(p.name + ".br")
        gz_path = p.with_name(p.name + ".gz")

        if not args.force and _is_up_to_date(p, br_path) and _is_up_to_date(p, gz_path):
            # 已有最新壓縮檔，略過
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