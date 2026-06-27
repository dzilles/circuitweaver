"""Transform modules for CircuitWeaver.

This package handles data transformations between types:
- source_to_layout: Source elements → Layout graph (ELK input)
- layout_to_schematic: Layout graph (ELK output) → Schematic elements
- schematic_to_s_expr: Schematic elements → S-expression tree
"""

from circuitweaver.transform.layout_to_schematic import (
    LayoutToSchematicTransform,
    snap_to_grid,
)
from circuitweaver.transform.schematic_to_s_expr import (
    SchematicToSExprTransform,
)
from circuitweaver.transform.source_to_layout import (
    FTYPE_SYMBOL_MAP,
    LayoutRegistry,
    SourceToLayoutTransform,
    get_effective_symbol_id,
)

__all__ = [
    # Source → Layout
    "SourceToLayoutTransform",
    "LayoutRegistry",
    "FTYPE_SYMBOL_MAP",
    "get_effective_symbol_id",
    # Layout → Schematic
    "LayoutToSchematicTransform",
    "snap_to_grid",
    # Schematic → S-expr
    "SchematicToSExprTransform",
]
