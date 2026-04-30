# I/O and Validation Requirements

## JSON I/O

- [implemented] `IO-001` `read_circuit` shall load a JSON file and require the top-level value to be a list.
- [implemented] `IO-002` `read_circuit` shall parse source and schematic element types.
- [implemented] `IO-003` `read_source` shall load only source element types and reject schematic element types.
- [implemented] `IO-004` `read_schematic` shall load only schematic element types and reject source element types.
- [implemented] `IO-005` `write_circuit` shall write all provided circuit elements as JSON using aliases.
- [implemented] `IO-006` `write_source` shall write only elements whose type starts with `source_`.
- [implemented] `IO-007` `write_schematic` shall write only elements whose type starts with `schematic_`.
- [implemented] `IO-008` `read_layout` shall parse a JSON file into a `LayoutNode`.
- [implemented] `IO-009` `write_layout` shall serialize a `LayoutNode` to JSON.
- [implemented] `IO-010` `parse_element` shall reject missing `type` fields.
- [implemented] `IO-011` `parse_element` shall reject unknown element types and list valid types in the error message.
- [implemented] `IO-012` `get_element_id_from_raw` shall prefer the ID field implied by the raw element's `type`, shall fall back to the first supported ID field when `type` is missing or unknown, and shall return `None` when no supported ID field exists.
- [implemented] `IO-013` `get_unknown_fields` shall return raw JSON object fields that are not defined by the model selected by the element's `type`.
- [implemented] `IO-014` `describe_unknown_field` shall explain that unknown fields are ignored by CircuitWeaver and shall include supported replacement guidance when the unknown field is a known likely authoring mistake.

## S-Expression I/O

- [implemented] `IO-020` `read_s_expr` shall read text with UTF-8 and `errors="replace"` and parse it as an `SExpr`.
- [implemented] `IO-021` `write_s_expr` shall serialize an `SExpr` and write UTF-8 text.
- [implemented] `IO-022` `format_value(None)` shall serialize to an empty string.
- [implemented] `IO-023` `format_value(True)` shall serialize to `yes`; `format_value(False)` shall serialize to `no`.
- [implemented] `IO-024` Strings shall be quoted when they contain special characters, are empty, or are all digits.
- [implemented] `IO-025` `parse` shall raise `ParseError` for empty input or malformed S-expressions.
- [implemented] `IO-026` Parsed atoms shall become booleans for `yes`/`no`, integers when possible, floats when containing `.`, and strings otherwise.

## Validation Flow

- [implemented] `VAL-001` `validate_circuit_file` shall return a `ValidationResult` rather than raising for file-not-found, JSON parse, top-level structure, schema, or rule validation failures.
- [implemented] `VAL-002` Invalid JSON shall produce an error with rule `json_parse`.
- [implemented] `VAL-003` Missing files shall produce an error with rule `file_not_found`.
- [implemented] `VAL-004` Non-list top-level JSON shall produce an error with rule `structure`.
- [implemented] `VAL-005` Non-object list elements shall produce an error with rule `structure`.
- [implemented] `VAL-006` Elements missing `type` shall produce an error with rule `structure`.
- [implemented] `VAL-007` Pydantic schema validation failures shall produce errors with rule `schema`.
- [implemented] `VAL-008` Unknown element types shall produce errors with rule `schema`.
- [implemented] `VAL-009` If any structure or schema errors exist, rule validation shall not run.
- [implemented] `VAL-010` `ValidationResult.is_valid` shall be true only when there are zero errors.
- [implemented] `VAL-011` `ValidationResult.to_dict` shall include `is_valid`, `error_count`, `warning_count`, `errors`, and `warnings`.
- [implemented] `VAL-012` `validate_circuit_file` shall produce a warning with rule `unknown_field` for every raw element field that is not defined by the element model.
- [implemented] `VAL-013` Unknown-field warnings shall include the element type, element ID when available, ignored field name, and a statement that the field will not affect validation, layout, or KiCad output.
- [implemented] `VAL-014` Unknown `source_net_id` on a `source_trace` shall warn that `connected_source_net_ids: ["<source_net_id>"]` is the supported field for assigning a trace to a source net.

## Active Validation Rules

- [implemented] `VAL-020` The active validation rule order shall be `UniqueIdsRule`, `SourceReferencesRule`, `TraceConnectionsRule`, `SourcePortCompletenessRule`, and `DanglingLabelsRule`.
- [implemented] `VAL-021` Only active rules in `VALIDATION_RULES` shall be assumed to run during `validate_circuit_file`.

## Unique IDs

- [implemented] `VAL-030` Duplicate source IDs shall be errors.
- [implemented] `VAL-031` Source ID uniqueness shall be checked independently for `source_component`, `source_port`, `source_net`, `source_trace`, and `source_group` namespaces.
- [implemented] `VAL-032` Schematic IDs shall not be checked by `UniqueIdsRule`.

## Source References

- [implemented] `VAL-040` Every `SourcePort.source_component_id` shall reference an existing `SourceComponent`.
- [implemented] `VAL-041` Every `SourceTrace.connected_source_port_ids` entry shall reference an existing `SourcePort`.
- [implemented] `VAL-042` Every `SourceTrace.connected_source_net_ids` entry shall reference an existing `SourceNet`.
- [implemented] `VAL-043` A `SourceGroup.parent_source_group_id`, when present, shall reference an existing `SourceGroup`.
- [implemented] `VAL-044` If any `SourceGroup.subcircuit_id` values exist, source elements with a `subcircuit_id` not in that set shall produce warnings, not errors.

## Trace Connections

- [implemented] `VAL-050` Every `SourceTrace` shall contain at least one connected source port.
- [implemented] `VAL-051` Duplicate source port references within one `SourceTrace` shall be errors.
- [implemented] `VAL-052` Duplicate source net references within one `SourceTrace` shall be warnings.
- [implemented] `VAL-053` A `SourceTrace` with exactly one port and no nets shall produce a floating-connection warning.
- [implemented] `VAL-054` A source port appearing in multiple traces shall produce a warning.

## Source Port Completeness

- [implemented] `VAL-060` A `SourceComponent` without `symbol_id` shall produce a warning because symbol pin completeness cannot be checked.
- [implemented] `VAL-061` A `SourcePort` with `do_not_connect=true` shall produce a warning.
- [implemented] `VAL-062` A `SourceComponent` with a `symbol_id` shall have its expected pins loaded through `get_symbol_info`.
- [implemented] `VAL-063` If symbol pinout loading fails, validation shall produce an error for that component.
- [implemented] `VAL-064` For each expected symbol pin, a corresponding `SourcePort` shall exist by matching either `pin_number` or `name`.
- [implemented] `VAL-065` Missing expected symbol pins shall be validation errors.

## Dangling Labels

- [implemented] `VAL-070` Dangling label validation shall derive port-to-net mapping from `SourceTrace` elements.
- [implemented] `VAL-071` For a source trace with connected nets, only the first connected net ID shall be used for label connectivity mapping.
- [implemented] `VAL-072` `SchematicPort`, `SchematicHierarchicalPin`, and `SchematicTrace` endpoints shall contribute net presence at rounded `(sheet_id, x, y)` coordinates.
- [implemented] `VAL-073` A `SchematicNetLabel` or `SchematicHierarchicalLabel` at rounded coordinate `(0, 0)` shall produce a warning.
- [implemented] `VAL-074` A label whose `source_net_id` is not present at its rounded coordinate on its sheet shall produce a warning.
