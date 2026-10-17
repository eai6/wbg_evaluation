"""Template context: a version stamp for static assets, so a reload always fetches the current JS/CSS
(the dev server lets browsers reuse cached copies otherwise)."""
from pathlib import Path

_STATIC = Path(__file__).resolve().parent / "static" / "explorer"


def assets(request):
    return {"asset_v": int(max(p.stat().st_mtime for p in _STATIC.iterdir()))}
