import pytest
from circuitweaver.library.pinout import get_symbol_info

def test_get_symbol_info_resistor():
    """Test that a standard resistor symbol has non-zero dimensions from graphics."""
    info = get_symbol_info("Device:R")
    assert info.symbol_id == "Device:R"
    assert len(info.pins) == 2
    # Resistor should have width and height from graphics (rectangle)
    assert info.width > 0
    assert info.height > 0
    # standard KiCad R is approx 100mils wide (8 grid units) and 300mils long (24 grid units)
    # The result we saw earlier was Width: 16, Height: 40 which is reasonable
    assert info.width >= 8
    assert info.height >= 20

def test_get_symbol_info_capacitor():
    """Test another standard symbol."""
    info = get_symbol_info("Device:C")
    assert info.width > 0
    assert info.height > 0

def test_get_symbol_info_invalid():
    """Test error handling for missing library/symbol."""
    with pytest.raises(ValueError, match="Library file not found"):
        get_symbol_info("NonExistentLib:R")
    
    with pytest.raises(ValueError, match="Symbol 'NonExistentSym' not found"):
        get_symbol_info("Device:NonExistentSym")
