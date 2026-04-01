"""KiCad library path detection."""

import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class LibraryPaths:
    """Paths to KiCad libraries."""

    symbols: Optional[Path] = None
    footprints: Optional[Path] = None
    models_3d: Optional[Path] = None
    templates: Optional[Path] = None


def get_library_paths() -> LibraryPaths:
    """Detect KiCad library paths.

    Checks common installation locations based on the operating system.

    Returns:
        LibraryPaths with detected paths (None if not found).
    """
    paths = LibraryPaths()

    # Check environment variables first
    env_symbols = os.environ.get("KICAD_SYMBOL_DIR")
    env_footprints = os.environ.get("KICAD_FOOTPRINT_DIR")
    env_3dmodels = os.environ.get("KICAD_3DMODEL_DIR")

    if env_symbols and Path(env_symbols).exists():
        paths.symbols = Path(env_symbols)
    if env_footprints and Path(env_footprints).exists():
        paths.footprints = Path(env_footprints)
    if env_3dmodels and Path(env_3dmodels).exists():
        paths.models_3d = Path(env_3dmodels)

    # If not set via env, check common locations
    system = platform.system()

    if system == "Linux":
        candidates = _get_linux_paths()
    elif system == "Darwin":
        candidates = _get_macos_paths()
    elif system == "Windows":
        candidates = _get_windows_paths()
    else:
        candidates = []

    for candidate in candidates:
        if paths.symbols is None:
            sym_path = candidate / "symbols"
            if sym_path.exists():
                paths.symbols = sym_path

        if paths.footprints is None:
            fp_path = candidate / "footprints"
            if fp_path.exists():
                paths.footprints = fp_path

        if paths.models_3d is None:
            models_path = candidate / "3dmodels"
            if models_path.exists():
                paths.models_3d = models_path

        if paths.templates is None:
            templates_path = candidate / "templates"
            if templates_path.exists():
                paths.templates = templates_path

    return paths


def _get_linux_paths() -> list[Path]:
    """Get candidate paths for Linux."""
    candidates = []

    # Standard package manager locations
    for version in ["10.0", "9.0", "8.0", "7.0"]:
        candidates.append(Path(f"/usr/share/kicad/{version}"))
        candidates.append(Path(f"/usr/share/kicad"))

    # Flatpak
    candidates.append(Path.home() / ".var/app/org.kicad.KiCad/data/kicad")

    # User local
    candidates.append(Path.home() / ".local/share/kicad")

    return candidates


def _get_macos_paths() -> list[Path]:
    """Get candidate paths for macOS."""
    candidates = []

    # Standard app bundle
    candidates.append(Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport"))

    # Homebrew
    for version in ["10.0", "9.0", "8.0", "7.0"]:
        candidates.append(Path(f"/usr/local/share/kicad/{version}"))
        candidates.append(Path(f"/opt/homebrew/share/kicad/{version}"))

    # User library
    candidates.append(Path.home() / "Library/Application Support/kicad")

    return candidates


def _get_windows_paths() -> list[Path]:
    """Get candidate paths for Windows."""
    candidates = []

    # Standard installation
    program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
    for version in ["10.0", "9.0", "8.0", "7.0"]:
        candidates.append(Path(program_files) / f"KiCad\\{version}\\share\\kicad")
        candidates.append(Path(program_files) / f"KiCad\\share\\kicad\\{version}")

    # User data
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        candidates.append(Path(appdata) / "kicad")

    return candidates


def find_kicad_cli() -> Optional[Path]:
    """Find the kicad-cli executable.

    Returns:
        Path to kicad-cli if found, None otherwise.
    """
    import shutil

    # Check PATH first
    cli = shutil.which("kicad-cli")
    if cli:
        return Path(cli)

    # Check common locations
    system = platform.system()

    if system == "Linux":
        candidates = [
            Path("/usr/bin/kicad-cli"),
            Path("/usr/local/bin/kicad-cli"),
        ]
    elif system == "Darwin":
        candidates = [
            Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"),
            Path("/usr/local/bin/kicad-cli"),
            Path("/opt/homebrew/bin/kicad-cli"),
        ]
    elif system == "Windows":
        program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
        candidates = [
            Path(program_files) / "KiCad" / "10.0" / "bin" / "kicad-cli.exe",
            Path(program_files) / "KiCad" / "bin" / "kicad-cli.exe",
        ]
    else:
        candidates = []

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return None
