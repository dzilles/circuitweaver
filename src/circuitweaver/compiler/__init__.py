"""Compiler for Circuit JSON to KiCad schematic format.

NOTE: The compiler requires schematic_* elements which are generated
by the auto-layout tool (Phase 2). Currently not implemented.
"""

from pathlib import Path


def compile_to_kicad(input_file: Path, output_dir: Path) -> list[Path]:
    """Compile Circuit JSON to KiCad schematic.

    NOTE: Not yet implemented. Requires auto-layout tool (Phase 2)
    to generate schematic_* elements from source_* elements.
    """
    raise NotImplementedError(
        "Compiler not yet implemented. "
        "Requires auto-layout tool (Phase 2) to generate schematic elements."
    )


__all__ = ["compile_to_kicad"]
