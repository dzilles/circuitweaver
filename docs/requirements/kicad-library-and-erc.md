# KiCad Library and ERC Requirements

## KiCad Path Discovery

- [implemented] `KICAD-001` KiCad symbol, footprint, and 3D model paths shall be read from `KICAD_SYMBOL_DIR`, `KICAD_FOOTPRINT_DIR`, and `KICAD_3DMODEL_DIR` when those environment variables exist and point to existing paths.
- [implemented] `KICAD-002` If environment variables do not resolve all paths, platform-specific default locations shall be searched.
- [implemented] `KICAD-003` Linux default path candidates shall include `/usr/share/kicad/<version>`, `/usr/share/kicad`, Flatpak user data, and `~/.local/share/kicad`.
- [implemented] `KICAD-004` macOS default path candidates shall include the KiCad app bundle support path, Homebrew paths, and `~/Library/Application Support/kicad`.
- [implemented] `KICAD-005` Windows default path candidates shall include Program Files KiCad share paths and `%APPDATA%/kicad`.
- [implemented] `KICAD-006` `find_kicad_cli` shall search `PATH` before platform-specific candidate executable paths.

## Part Search

- [implemented] `KICAD-010` `search_parts` shall search built-in parts before installed KiCad libraries.
- [implemented] `KICAD-011` Search matching shall be case-insensitive.
- [implemented] `KICAD-012` Every query word shall match the concatenated searchable fields for a part.
- [implemented] `KICAD-013` Built-in search fields shall include library ID, symbol name, description, and keywords.
- [implemented] `KICAD-014` Search shall return at most the requested limit.
- [implemented] `KICAD-015` KiCad library search shall scan `*.kicad_sym` files in the detected symbol path.
- [implemented] `KICAD-016` KiCad library search shall skip symbols whose names appear to be numeric sub-units ending in `_N`.
- [implemented] `KICAD-017` KiCad library search shall extract description, keywords, and footprint properties with regular expressions.
- [implemented] `KICAD-018` KiCad library parse failures shall be logged and skipped rather than aborting the whole search.

## Symbol Pinout Extraction

- [implemented] `KICAD-030` `get_symbol_info` shall accept symbol IDs in `Library:Symbol` form.
- [implemented] `KICAD-031` `get_symbol_info` shall load `<Library>.kicad_sym` from the detected symbol library directory.
- [implemented] `KICAD-032` Missing library files shall raise `ValueError`.
- [implemented] `KICAD-033` Malformed symbol library S-expressions shall raise `ValueError`.
- [implemented] `KICAD-034` Missing symbols shall raise `ValueError`.
- [implemented] `KICAD-035` KiCad symbol inheritance through `extends` shall be resolved when extracting pins and bounds.
- [implemented] `KICAD-036` Pins shall be found recursively in nested symbol blocks.
- [implemented] `KICAD-037` Pin numbers shall come from the KiCad `number` property when present, otherwise `?`.
- [implemented] `KICAD-038` Pin names shall come from the KiCad `name` property when present, otherwise `?`.
- [implemented] `KICAD-039` Pin electrical type shall come from the KiCad pin expression's second item when present, otherwise `passive`.
- [implemented] `KICAD-040` Pin coordinates shall convert millimeters to grid units using `0.127 mm` per grid unit.
- [implemented] `KICAD-041` Pin Y coordinates shall be negated when converting from symbol coordinates to schematic coordinates.
- [implemented] `KICAD-042` Pin direction shall map KiCad angle `0` to `right`, `90` to `up`, `180` to `left`, and `270` to `down`; unknown angles shall default to `right`.
- [implemented] `KICAD-043` Symbol bounds shall be computed from graphical primitives and pins.
- [implemented] `KICAD-044` Symbols with no geometry and no pins shall raise `ValueError`.
- [implemented] `KICAD-045` `get_symbol_info` results shall be cached with an LRU cache.

## Embedded Symbol Definitions

- [implemented] `KICAD-050` `get_expanded_symbol_definition` shall extract a balanced symbol S-expression from a KiCad library file.
- [implemented] `KICAD-051` `get_expanded_symbol_definition` shall recursively inline inherited base symbol content when an `extends` expression is present.
- [implemented] `KICAD-052` `get_expanded_symbol_definition` shall optionally rename the symbol and internal unit references when `rename_to` is provided.
- [implemented] `KICAD-053` `get_expanded_symbol_definition` results shall be cached with an LRU cache.

## ERC

- [implemented] `ERC-001` `ERCChecker.run` shall require the schematic path to exist and shall raise `FileNotFoundError` otherwise.
- [implemented] `ERC-002` `ERCChecker.run` shall execute `kicad-cli sch erc <schematic> --format json --output <report>`.
- [implemented] `ERC-003` ERC reports shall be written to a temporary JSON file.
- [implemented] `ERC-004` If no ERC report is generated, the result shall be invalid and contain an error with captured CLI output.
- [implemented] `ERC-005` If the ERC report cannot be parsed as JSON, the result shall be invalid and contain a parse error.
- [implemented] `ERC-006` KiCad 10 report parsing shall read violations from `data["sheets"][*]["violations"]`.
- [implemented] `ERC-007` Violations with severity `error` shall be returned in `errors`.
- [implemented] `ERC-008` Violations with other severities shall be returned in `warnings`.
- [implemented] `ERC-009` Parsed violation messages shall include type, description, and first item position when available.
- [implemented] `ERC-010` ERC result dictionaries shall include `is_valid`, `errors`, `warnings`, and `total_violations` when a report is parsed.

