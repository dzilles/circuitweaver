"""Unit tests for logic-only validation and source types."""

import json
from pathlib import Path
import pytest
from circuitweaver.validator import validate_circuit_file

def test_source_group_validation(tmp_path: Path):
    """Test that source_group and its hierarchy are validated correctly."""
    circuit = [
        {
            "type": "source_group",
            "source_group_id": "group_1",
            "name": "Main Board",
            "subcircuit_id": "main"
        },
        {
            "type": "source_group",
            "source_group_id": "group_2",
            "name": "Power Section",
            "subcircuit_id": "power",
            "parent_source_group_id": "group_1"
        },
        {
            "type": "source_component",
            "source_component_id": "u1",
            "name": "U1",
            "subcircuit_id": "power"
        }
    ]
    file_path = tmp_path / "groups.json"
    file_path.write_text(json.dumps(circuit))
    
    result = validate_circuit_file(file_path)
    assert result.is_valid

def test_source_group_invalid_parent(tmp_path: Path):
    """Test that an invalid parent_source_group_id is caught."""
    circuit = [
        {
            "type": "source_group",
            "source_group_id": "group_1",
            "name": "Main Board",
            "parent_source_group_id": "non_existent"
        }
    ]
    file_path = tmp_path / "bad_group.json"
    file_path.write_text(json.dumps(circuit))
    
    result = validate_circuit_file(file_path)
    assert not result.is_valid
    assert any("non-existent parent_source_group_id" in str(e) for e in result.errors)

def test_source_trace_new_format(tmp_path: Path):
    """Test the new SourceTrace format with optional nets and metadata."""
    circuit = [
        {"type": "source_component", "source_component_id": "r1", "name": "R1"},
        {"type": "source_port", "source_port_id": "p1", "source_component_id": "r1", "name": "1"},
        {"type": "source_port", "source_port_id": "p2", "source_component_id": "r1", "name": "2"},
        {"type": "source_net", "source_net_id": "net1", "name": "VCC"},
        {
            "type": "source_trace",
            "source_trace_id": "trace1",
            "connected_source_port_ids": ["p1", "p2"],
            "connected_source_net_ids": ["net1"],
            "display_name": "Power Trace",
            "max_length": 10.5
        }
    ]
    file_path = tmp_path / "trace_format.json"
    file_path.write_text(json.dumps(circuit))
    
    result = validate_circuit_file(file_path)
    assert result.is_valid

def test_source_references_all_types(tmp_path: Path):
    """Test all types of source references."""
    circuit = [
        # Valid component and net
        {"type": "source_component", "source_component_id": "c1", "name": "C1"},
        {"type": "source_net", "source_net_id": "n1", "name": "GND"},
        # Valid port
        {"type": "source_port", "source_port_id": "port1", "source_component_id": "c1", "name": "1"},
        # Valid trace
        {
            "type": "source_trace",
            "source_trace_id": "t1",
            "connected_source_port_ids": ["port1"],
            "connected_source_net_ids": ["n1"]
        }
    ]
    file_path = tmp_path / "refs.json"
    file_path.write_text(json.dumps(circuit))
    
    result = validate_circuit_file(file_path)
    assert result.is_valid

def test_missing_subcircuit_id_warning(tmp_path: Path):
    """Test that referencing an undefined subcircuit_id produces a warning."""
    circuit = [
        {"type": "source_group", "source_group_id": "g1", "subcircuit_id": "real_sub"},
        {
            "type": "source_component", 
            "source_component_id": "c1", 
            "name": "C1", 
            "subcircuit_id": "fake_sub"
        }
    ]
    file_path = tmp_path / "subcircuit_warn.json"
    file_path.write_text(json.dumps(circuit))
    
    result = validate_circuit_file(file_path)
    # It should be valid but have a warning
    assert result.is_valid
    assert any("references subcircuit_id 'fake_sub' which is not defined" in str(w) for w in result.warnings)

def test_trace_duplicate_ports(tmp_path: Path):
    """Test that duplicate ports in a trace are caught."""
    circuit = [
        {"type": "source_component", "source_component_id": "r1", "name": "R1"},
        {"type": "source_port", "source_port_id": "p1", "source_component_id": "r1", "name": "1"},
        {
            "type": "source_trace",
            "source_trace_id": "t1",
            "connected_source_port_ids": ["p1", "p1"]
        }
    ]
    file_path = tmp_path / "dup_trace_ports.json"
    file_path.write_text(json.dumps(circuit))
    
    result = validate_circuit_file(file_path)
    assert not result.is_valid
    assert any("references port 'p1' multiple times" in str(e) for e in result.errors)
