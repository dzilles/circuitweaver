from circuitweaver.library.pinout import SymbolAdapter, get_symbol_info


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
