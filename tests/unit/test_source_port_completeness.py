"""Unit tests for SourcePortCompletenessRule."""

import json
from pathlib import Path
import pytest
from circuitweaver.validator import validate_circuit_file

def test_missing_symbol_id_warning(tmp_path: Path):
    """Test that a component without symbol_id results in a warning."""
    circuit = [
        {"type": "source_component", "source_component_id": "c1", "name": "R1"}
    ]
    file_path = tmp_path / "warn.json"
    file_path.write_text(json.dumps(circuit))
    
    result = validate_circuit_file(file_path)
    assert result.is_valid
    assert any("missing 'symbol_id'" in str(w) for w in result.warnings)

def test_missing_port_error(tmp_path: Path):
    """Test that a component with symbol_id but missing ports results in errors."""
    # Device:R has 2 pins (1 and 2)
    circuit = [
        {
            "type": "source_component", 
            "source_component_id": "r1", 
            "name": "R1", 
            "symbol_id": "Device:R"
        },
        # Only define one port
        {
            "type": "source_port",
            "source_port_id": "p1",
            "source_component_id": "r1",
            "name": "1",
            "pin_number": 1
        }
    ]
    file_path = tmp_path / "error.json"
    file_path.write_text(json.dumps(circuit))
    
    result = validate_circuit_file(file_path)
    assert not result.is_valid
    assert any("missing port definition for symbol pin 2" in str(e) for e in result.errors)

def test_complete_ports_success(tmp_path: Path):
    """Test that a component with all pins defined passes."""
    circuit = [
        {
            "type": "source_component", 
            "source_component_id": "r1", 
            "name": "R1", 
            "symbol_id": "Device:R"
        },
        {
            "type": "source_port",
            "source_port_id": "p1",
            "source_component_id": "r1",
            "name": "1",
            "pin_number": 1
        },
        {
            "type": "source_port",
            "source_port_id": "p2",
            "source_component_id": "r1",
            "name": "2",
            "pin_number": 2
        }
    ]
    file_path = tmp_path / "success.json"
    file_path.write_text(json.dumps(circuit))
    
    result = validate_circuit_file(file_path)
    assert result.is_valid
    assert len(result.errors) == 0

def test_invalid_symbol_id_error(tmp_path: Path):
    """Test that an invalid symbol_id results in an error."""
    circuit = [
        {
            "type": "source_component", 
            "source_component_id": "c1", 
            "name": "U1", 
            "symbol_id": "NonExistent:Symbol"
        }
    ]
    file_path = tmp_path / "bad_symbol.json"
    file_path.write_text(json.dumps(circuit))
    
    result = validate_circuit_file(file_path)
    assert not result.is_valid
    assert any("Could not fetch pinout for symbol 'NonExistent:Symbol'" in str(e) for e in result.errors)
