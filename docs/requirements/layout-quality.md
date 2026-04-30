# Layout Quality Requirements

These requirements describe a first practical target for readable generated
schematics. They are intentionally limited to behavior that can be implemented
and tested incrementally.

## Basic Flow

- [implemented] `LQ-001` Generated sheets shall prefer a left-to-right ELK layout direction.
- [missing] `LQ-002` Root-page hierarchical sheet boxes shall be ordered left-to-right when their inter-sheet connections imply an upstream-to-downstream relationship.
- [missing] `LQ-003` Components with mostly input-side connections should be placed left of components with mostly output-side connections when this can be inferred from graph connectivity.
- [partial] `LQ-004` If flow direction cannot be inferred, the layout shall still produce a stable deterministic order.
  Source groups, components, fallback ports, hierarchical pins, and per-sheet connectivity are sorted before ELK input generation. Final coordinates can still depend on ELK behavior.

## Containment

- [missing] `LQ-020` Components assigned to a child sheet shall be generated on that child sheet, not on the root sheet.
- [missing] `LQ-021` Components assigned to a group box shall be positioned inside the group box.
- [missing] `LQ-022` Group boxes shall be large enough to contain their child components with padding.
- [missing] `LQ-023` Hierarchical pins shall be placed on the boundary of their owning sheet box.
- [missing] `LQ-024` Sheet boxes shall be large enough that hierarchical pins and sheet fields do not overlap each other.

## No Obvious Overlaps

- [missing] `LQ-040` Generated component bounding boxes shall not overlap each other on the same sheet.
- [missing] `LQ-041` Generated labels shall not overlap component bounding boxes on the same sheet.
- [missing] `LQ-042` Generated labels shall not overlap other labels on the same sheet.
- [missing] `LQ-043` Hierarchical pins on the same sheet box edge shall not overlap each other.
- [missing] `LQ-044` Sheet boxes on the root page shall not overlap each other.

## Label Placement

- [missing] `LQ-060` Labels generated for component ports shall be placed near the port they refer to.
- [missing] `LQ-061` Hierarchical labels inside child sheets shall not remain at `(0, 0)` after layout.
- [missing] `LQ-062` Global labels inside child sheets shall not remain at `(0, 0)` after layout.
- [missing] `LQ-063` Root-page labels for hierarchical sheet pins shall be placed at or near the matching sheet pin.

## Routing

- [missing] `LQ-080` Generated wires shall use orthogonal segments.
- [missing] `LQ-081` Generated wires shall not intentionally route through component bounding boxes.
- [missing] `LQ-082` Cross-sheet connections shall prefer labels on the root page rather than long wires between sheet boxes.

## Layout Quality Check

- [implemented] `LQ-100` The compiler shall provide a layout-quality check that can run after layout generation.
  `CompileEngine.check_layout_quality()` checks existing schematic elements or runs layout first for source-only input.
- [implemented] `LQ-101` The layout-quality check shall report overlapping components.
  Diagnostics use the violated layout rule ID `LQ-040`.
- [implemented] `LQ-102` The layout-quality check shall report labels at `(0, 0)`.
- [partial] `LQ-103` The layout-quality check shall report components outside their assigned group box or sheet.
  Group-box containment is checked when the source component and its generated `box_<source_group_id>` are present on the same sheet. Child-sheet ownership is not yet checked as a separate diagnostic.
- [implemented] `LQ-104` The layout-quality check shall report sheet boxes that overlap on the root page.
  Diagnostics use the violated layout rule ID `LQ-104`.
- [implemented] `LQ-105` Layout-quality diagnostics shall include the affected sheet ID and element IDs.
- [implemented] `LQ-106` The layout-quality check shall report labels that overlap component bounding boxes.
  Diagnostics use the violated layout rule ID `LQ-041`.
- [implemented] `LQ-107` The layout-quality check shall report labels that overlap other labels on the same sheet.
  Diagnostics use the violated layout rule ID `LQ-042`.
- [implemented] `LQ-108` The layout-quality check shall report hierarchical pins that occupy the same position on the same sheet box.
  Diagnostics use the violated layout rule ID `LQ-043`.
- [implemented] `LQ-109` The CLI shall expose layout-quality diagnostics in human-readable text and JSON formats.
