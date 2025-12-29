from .file import ensure_dir, ensure_file, add_prefix_to_filename

# Optional: FFmpegPipe pulls in heavier deps (e.g., matplotlib). Make import best-effort
# so light-weight utilities (like npy calibration) can still be used standalone.
try:
  from .FFmpegPipe import FFmpegPipe  # type: ignore
except Exception:  # pragma: no cover
  FFmpegPipe = None  # type: ignore

__all__ = [
  # ffmpeg
  "FFmpegPipe",

  # file
  "ensure_dir",
  "ensure_file",
  "add_prefix_to_filename",
]