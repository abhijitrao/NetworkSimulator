"""Platform-aware writable data directory selection."""
from __future__ import annotations

import os
from pathlib import Path
import sys
from collections.abc import Mapping


def get_data_dir(
    *,
    platform: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    app_dir: Path | None = None,
) -> Path:
    """Return the writable directory used for profiles and other user data.

    Windows keeps the existing portable layout beside the executable/project.
    Linux follows the XDG Base Directory convention so installations under
    /opt or /usr/local do not need write access to the application directory.
    """
    current_platform = platform or sys.platform
    environment = os.environ if environ is None else environ

    if current_platform.startswith("linux"):
        xdg_data_home = environment.get("XDG_DATA_HOME")
        if xdg_data_home:
            base = Path(xdg_data_home).expanduser()
        else:
            user_home = home if home is not None else Path.home()
            base = user_home / ".local" / "share"
        return base / "network-simulator"

    if app_dir is not None:
        return Path(app_dir) / "data"

    frozen = bool(getattr(sys, "frozen", False))
    application_dir = Path(sys.executable).resolve().parent if frozen else Path(__file__).resolve().parent.parent
    return application_dir / "data"
