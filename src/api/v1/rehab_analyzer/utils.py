from __future__ import annotations

from pathlib import Path, PureWindowsPath
from typing import Optional

import numpy as np
from fastapi import HTTPException

from api.config import NPY_DIR
from db import RealsensePoseExtractor


def _normalize_db_path(raw: str) -> Path:
    """
    Normalize a path string that may have been stored on Windows (backslashes / drive letters)
    so it can be used inside the Linux Docker container.

    Examples:
    - "data\\npy\\x.npy" -> "data/npy/x.npy"
    - "C:\\proj\\data\\npy\\x.npy" -> "data/npy/x.npy"  (best-effort)
    """
    s = (raw or "").strip()
    if not s:
        return Path(s)

    # Treat backslashes as separators (Windows-style stored paths)
    if "\\" in s:
        pw = PureWindowsPath(s)
        parts = list(pw.parts)

        # Drop drive/root if present (e.g. "C:\\")
        if pw.drive:
            parts = parts[1:]

        # If path contains a "data" segment, map to repo-relative "data/<...>"
        lower = [p.lower() for p in parts]
        if "data" in lower:
            i = lower.index("data")
            return Path("data").joinpath(*parts[i + 1 :])

        # Fallback: just convert separators
        return Path(s.replace("\\", "/"))

    return Path(s)

async def resolve_session_npy_path(session_name: str) -> str:
    """Return the npy_path for a session or raise 400 if the session is missing."""
    try:
        existing = await RealsensePoseExtractor.find_one(
            RealsensePoseExtractor.session_name == session_name
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"database connection failed: {e}",
            ) from None

    if not existing:
        raise HTTPException(
            status_code=400,
            detail=f"session {session_name} not found",
        )

    # Normalize DB-stored path (may have come from Windows) and ensure file exists.
    raw = existing.npy_path or ""
    candidate = _normalize_db_path(raw)

    # If DB path is empty or points nowhere, fall back to default convention.
    fallback = Path(NPY_DIR) / f"{session_name}.npy"

    # Resolve relative paths against current working directory (container uses /app)
    if str(candidate) and not candidate.is_absolute():
        candidate_abs = (Path.cwd() / candidate).resolve()
    else:
        candidate_abs = candidate

    if str(candidate_abs) and candidate_abs.exists():
        return str(candidate_abs)

    if fallback.exists():
        return str(fallback)

    raise HTTPException(
        status_code=404,
        detail=(
            f"npy file not found for session={session_name}. "
            f"expected one of: {candidate_abs!s} or {fallback!s}. "
            f"Please put the file under ./data/npy (host) so it is mounted to /app/data/npy in Docker, "
            f"or update HOST_DATA_DIR in your .env to point to the folder that contains the npy files."
        ),
    )

def select_peak_indices(
    f: np.ndarray,
    values_db: np.ndarray,
    *,
    max_peaks: Optional[int],
    min_peak_distance_ratio: float,
    min_db: float,
    min_freq: float,
    ensure_global_peak: bool = False,
) -> list[int]:
    """
    Select peak indices from a spectrum with optional global-peak guarantee.
    Shared by multiple API endpoints to keep peak picking consistent.
    """
    if (
        max_peaks is None
        or max_peaks <= 0
        or values_db.size <= 2
        or f.size == 0
    ):
        return []

    f_min, f_max = float(f.min()), float(f.max())
    f_span = max(f_max - f_min, 1e-9)
    min_df = min_peak_distance_ratio * f_span

    # Filter out invalid / low-power / out-of-range points
    mask = np.isfinite(values_db)
    mask &= values_db >= min_db
    mask &= f >= max(min_freq, f_min)
    mask &= f <= f_max
    idx_all = np.nonzero(mask)[0]
    if idx_all.size == 0:
        return []

    # Optionally force-include the global strongest peak
    best_idx_global = (
        int(idx_all[np.nanargmax(values_db[idx_all])])
        if ensure_global_peak
        else None
    )

    # Local maxima candidates
    idx_candidates: list[int] = []
    for idx in idx_all:
        if idx == 0 or idx == values_db.size - 1:
            continue
        if values_db[idx] >= values_db[idx - 1] and values_db[idx] >= values_db[idx + 1]:
            idx_candidates.append(idx)

    if ensure_global_peak and best_idx_global is not None and best_idx_global not in idx_candidates:
        idx_candidates.append(best_idx_global)

    if not idx_candidates:
        return []

    order = np.argsort(values_db[idx_candidates])[::-1]
    idx_sorted = np.asarray(idx_candidates, dtype=int)[order]

    chosen: list[int] = []
    for idx in idx_sorted:
        if len(chosen) >= max_peaks:
            break
        # Keep minimum frequency spacing between peaks
        if not chosen or all(abs(f[idx] - f[j]) >= min_df for j in chosen):
            chosen.append(idx)
    return chosen