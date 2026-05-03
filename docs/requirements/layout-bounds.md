# Layout Bounds Requirements

These requirements define how generated schematics should stay inside an
explicit usable drawing area. They are target behavior for future work and are
intended to make page fit, overflow handling, and layout validation testable.

## Layout Configuration Model

- [missing] `LB-001` Circuit JSON shall support project-level layout configuration under `source_project_config`.
- [missing] `LB-002` The layout configuration shall support a project-wide paper size such as `A4`.
- [missing] `LB-003` The layout configuration shall support a project-wide orientation, at least `portrait` and `landscape`.
- [missing] `LB-004` The layout configuration shall support a project-wide page margin in schematic grid units.
- [missing] `LB-005` The layout configuration shall support per-sheet usable bounds keyed by `sheet_id`.
- [missing] `LB-006` Per-sheet usable bounds shall include `x`, `y`, `width`, and `height` in schematic grid units.
- [missing] `LB-007` Per-sheet usable bounds shall override bounds derived from project-wide paper size, orientation, and margin.
- [missing] `LB-008` If no layout configuration is provided, the compiler shall preserve current layout behavior.
- [missing] `LB-009` Unknown or invalid layout configuration fields shall produce validation diagnostics rather than being silently treated as active layout constraints.

## Bound Resolution

- [missing] `LB-020` The compiler shall resolve an effective usable bounds rectangle for every generated sheet.
- [missing] `LB-021` Effective bounds shall be deterministic for the same input JSON and environment.
- [missing] `LB-022` The root sheet and each child sheet may have different effective bounds.
- [missing] `LB-023` Generated schematic elements shall be compared against usable bounds in the same coordinate system used by schematic elements.
- [missing] `LB-024` Bounds resolution shall account for configured margins before layout generation.
- [missing] `LB-025` Bounds resolution shall expose the effective bounds in layout debug artifacts when layout debug output is enabled.

## Layout Generation Constraints

- [missing] `LB-040` Source-to-layout generation shall pass effective usable bounds to the layout graph when bounds are configured.
- [missing] `LB-041` ELK root graph width and height shall be derived from the effective usable bounds when bounds are configured.
- [missing] `LB-042` ELK padding shall be derived from configured margins or effective bounds rather than hard-coded padding when bounds are configured.
- [missing] `LB-043` Components shall be initially placed only inside the effective usable bounds for their sheet.
- [missing] `LB-044` Labels shall be initially placed only inside the effective usable bounds for their sheet.
- [missing] `LB-045` Group boxes and hierarchical sheet boxes shall be initially placed only inside the effective usable bounds for their owning sheet.
- [missing] `LB-046` Hierarchical pins shall remain on their owning sheet box boundary and inside the effective usable bounds.
- [missing] `LB-047` Generated wire segments shall not intentionally leave the effective usable bounds.
- [missing] `LB-048` Keeping elements inside bounds shall not be implemented by blind coordinate clamping that can create overlaps or disconnect labels from referenced ports.

## Overflow Policy

- [missing] `LB-060` Layout configuration shall support an overflow policy.
- [missing] `LB-061` The overflow policy shall support `strict`, which reports diagnostics when generated content does not fit inside effective bounds.
- [missing] `LB-062` The overflow policy shall support `expand`, which grows the output sheet size or usable bounds when content does not fit.
- [missing] `LB-063` The compiler shall default to `strict` when explicit bounds are configured and no overflow policy is provided.
- [missing] `LB-064` The compiler shall not silently switch from `strict` to `expand`.
- [missing] `LB-065` If `strict` overflow is selected and content cannot fit, compilation shall still produce actionable diagnostics that identify the sheet and offending elements.
- [missing] `LB-066` If `expand` overflow is selected, generated KiCad sheet metadata shall reflect the expanded page size when KiCad supports that size.
- [missing] `LB-067` If `expand` overflow is selected but the output format cannot represent the expanded bounds, the compiler shall report a diagnostic instead of emitting misleading page metadata.
- [missing] `LB-068` Future overflow policies such as `paginate` or `scale` shall not be implied by `strict` or `expand`.

## Layout Quality Diagnostics

- [missing] `LB-080` The layout-quality check shall report components outside effective usable bounds.
- [missing] `LB-081` The layout-quality check shall report labels outside effective usable bounds.
- [missing] `LB-082` The layout-quality check shall report group boxes outside effective usable bounds.
- [missing] `LB-083` The layout-quality check shall report hierarchical sheet boxes outside effective usable bounds.
- [missing] `LB-084` The layout-quality check shall report hierarchical pins outside effective usable bounds.
- [missing] `LB-085` The layout-quality check shall report wire segments outside effective usable bounds.
- [missing] `LB-086` Out-of-bounds diagnostics shall include the affected `sheet_id`, offending element IDs, and the effective bounds used for the check.
- [missing] `LB-087` Out-of-bounds diagnostics shall be available through `CompileEngine.check_layout_quality()`.
- [missing] `LB-088` Out-of-bounds diagnostics shall be available through the `check-layout` CLI in text and JSON output.

## Validation

- [missing] `LB-100` Validation shall reject layout bounds with non-positive `width` or `height`.
- [missing] `LB-101` Validation shall reject negative margins.
- [missing] `LB-102` Validation shall reject unsupported paper sizes.
- [missing] `LB-103` Validation shall reject unsupported orientations.
- [missing] `LB-104` Validation shall reject unsupported overflow policies.
- [missing] `LB-105` Validation shall warn when per-sheet bounds reference a sheet ID that cannot be resolved from source hierarchy or existing schematic elements.
- [missing] `LB-106` Validation shall warn when configured bounds are smaller than the minimum size required by explicit sheet boxes, hierarchical pins, or configured margins.

## KiCad Output

- [missing] `LB-120` KiCad schematic output shall use the configured paper size and orientation when layout configuration provides them.
- [missing] `LB-121` If per-sheet bounds imply different page sizes, KiCad schematic output shall represent those page sizes per sheet when supported.
- [missing] `LB-122` If configured bounds cannot be represented as a named KiCad paper size, the compiler shall either emit a supported custom page size or report a diagnostic.
- [missing] `LB-123` KiCad output shall not claim a smaller page size than the bounds required by generated schematic elements.

## Testability

- [missing] `LB-140` Requirement-traceable tests shall cover layout configuration parsing.
- [missing] `LB-141` Requirement-traceable tests shall cover effective bounds resolution.
- [missing] `LB-142` Requirement-traceable tests shall cover bounded ELK input generation.
- [missing] `LB-143` Requirement-traceable tests shall cover out-of-bounds layout-quality diagnostics.
- [missing] `LB-144` Requirement-traceable tests shall cover `strict` overflow behavior.
- [missing] `LB-145` Requirement-traceable tests shall cover `expand` overflow behavior.
- [missing] `LB-146` Requirement-traceable tests shall cover KiCad paper output for configured bounds.
