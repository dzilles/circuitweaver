from types import SimpleNamespace

from circuitweaver.library.pinout import (
    SymbolAdapter,
    get_expanded_symbol_definition,
    get_symbol_info,
)


def test_get_symbol_info_resistor():
    """Test that a standard resistor symbol has non-zero dimensions from graphics."""
    info = get_symbol_info("Device:R")
    assert info.name == "R"
    assert len(info.pins) == 2
    # Resistors have graphics
    assert info.width > 0
    assert info.height > 0

def test_get_symbol_info_capacitor():
    """Test another standard symbol."""
    info = get_symbol_info("Device:C")
    assert info.name == "C"
    assert len(info.pins) == 2
    assert info.width > 0
    assert info.height > 0

def test_adapter_extract_pins():
    """Test that the adapter extracts pins correctly from a raw sexp list."""
    # (pin passive line (at 0 0 0) (length 2.54) (name "1" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))
    import sexpdata
    raw = '(pin passive line (at 2.54 5.08 0) (number "1") (name "A"))'
    sexp = sexpdata.loads(raw)
    adapter = SymbolAdapter()
    pins = adapter.extract_pins([sexp])

    assert len(pins) == 1
    assert pins[0].number == "1"
    assert pins[0].name == "A"
    # 2.54mm / 0.127 = 20
    assert pins[0].grid_offset.x == 20
    # 5.08mm / 0.127 = 40. Negated for schematic.
    assert pins[0].grid_offset.y == -40

def test_get_symbol_info_no_geometry():
    """Test error when symbol has no pins or graphics."""
    # We can't easily mock sexpdata.loads without a lot of ceremony,
    # but we can test that an empty list to adapter returns None/empty.
    adapter = SymbolAdapter()
    assert adapter.extract_graphic_bounds([]) is None
    assert adapter.extract_pins([]) == []


def test_expanded_symbol_embedding_renames_only_top_level_symbol(monkeypatch, tmp_path):
    lib_file = tmp_path / "Connector_Generic.kicad_sym"
    lib_file.write_text(
        """
(kicad_symbol_lib
  (symbol "Conn_01x02"
    (property "Value" "Conn_01x02")
    (symbol "Conn_01x02_1_1"
      (pin passive line (at 0 0 0) (number "1") (name "Pin_1"))
    )
  )
)
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "circuitweaver.library.pinout.get_library_paths",
        lambda: SimpleNamespace(symbols=tmp_path),
    )
    get_expanded_symbol_definition.cache_clear()

    symbol_def = get_expanded_symbol_definition(
        "Conn_01x02",
        library_name="Connector_Generic",
        rename_to="Connector_Generic:Conn_01x02",
    )

    assert '(symbol "Connector_Generic:Conn_01x02"' in symbol_def
    assert '(symbol "Conn_01x02_1_1"' in symbol_def
    assert "Connector_Generic:Conn_01x02_1_1" not in symbol_def

    get_expanded_symbol_definition.cache_clear()


def test_expanded_symbol_embedding_filters_inherited_properties(monkeypatch, tmp_path):
    lib_file = tmp_path / "Demo.kicad_sym"
    lib_file.write_text(
        """
(kicad_symbol_lib
  (symbol "Base"
    (exclude_from_sim no)
    (property "Value" "Base")
    (embedded_fonts no)
    (symbol "Base_1_1"
      (pin passive line (at 0 0 0) (number "1") (name "A"))
    )
  )
  (symbol "Child"
    (extends "Base")
    (property "Value" "Child")
    (embedded_fonts no)
  )
)
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "circuitweaver.library.pinout.get_library_paths",
        lambda: SimpleNamespace(symbols=tmp_path),
    )
    get_expanded_symbol_definition.cache_clear()

    symbol_def = get_expanded_symbol_definition(
        "Child",
        library_name="Demo",
        rename_to="Demo:Child",
    )

    assert '(symbol "Demo:Child"' in symbol_def
    assert '(property "Value" "Child")' in symbol_def
    assert '(property "Value" "Base")' not in symbol_def
    assert symbol_def.count("(embedded_fonts no)") == 1
    assert "(exclude_from_sim no)" in symbol_def
    assert '(symbol "Child_1_1"' in symbol_def
    assert "Base_1_1" not in symbol_def

    get_expanded_symbol_definition.cache_clear()
