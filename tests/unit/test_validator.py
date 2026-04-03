"""Tests for the validation engine."""

import json
from pathlib import Path

import pytest

from circuitweaver.validator import validate_circuit_file, ValidationResult


class TestValidateCircuitFile:
    """Tests for validate_circuit_file function."""

    def test_valid_circuit(self, tmp_path: Path, simple_led_circuit: list[dict]):
        """Test that a valid circuit passes validation."""
        file_path = tmp_path / "valid.json"
        file_path.write_text(json.dumps(simple_led_circuit))

        result = validate_circuit_file(file_path)

        assert result.is_valid
        assert len(result.errors) == 0

    def test_invalid_json(self, tmp_path: Path):
        """Test that invalid JSON is caught."""
        file_path = tmp_path / "invalid.json"
        file_path.write_text("{ not valid json }")

        result = validate_circuit_file(file_path)

        assert not result.is_valid
        assert any("Invalid JSON" in str(e) for e in result.errors)

    def test_non_list_json(self, tmp_path: Path):
        """Test that non-list JSON is caught."""
        file_path = tmp_path / "object.json"
        file_path.write_text('{"type": "source_component"}')

        result = validate_circuit_file(file_path)

        assert not result.is_valid
        assert any("must be a list" in str(e) for e in result.errors)

    def test_missing_type_field(self, tmp_path: Path):
        """Test that elements without type field are caught."""
        file_path = tmp_path / "no_type.json"
        file_path.write_text('[{"name": "R1"}]')

        result = validate_circuit_file(file_path)

        assert not result.is_valid
        assert any("missing 'type'" in str(e) for e in result.errors)

    def test_unknown_type(self, tmp_path: Path):
        """Test that unknown element types are caught."""
        file_path = tmp_path / "unknown.json"
        file_path.write_text('[{"type": "unknown_type", "id": "x"}]')

        result = validate_circuit_file(file_path)

        assert not result.is_valid
        assert any("Unknown element type" in str(e) for e in result.errors)

    def test_file_not_found(self, tmp_path: Path):
        """Test that missing file is handled."""
        file_path = tmp_path / "nonexistent.json"

        result = validate_circuit_file(file_path)

        assert not result.is_valid
        assert any("not found" in str(e).lower() for e in result.errors)


class TestUniqueIds:
    """Tests for unique ID validation."""

    def test_duplicate_component_id(self, tmp_path: Path):
        """Test that duplicate component IDs are caught."""
        circuit = [
            {"type": "source_component", "source_component_id": "comp_1", "name": "R1"},
            {"type": "source_component", "source_component_id": "comp_1", "name": "R2"},
        ]
        file_path = tmp_path / "dup.json"
        file_path.write_text(json.dumps(circuit))

        result = validate_circuit_file(file_path)

        assert not result.is_valid
        assert any("Duplicate" in str(e) for e in result.errors)

    def test_duplicate_port_id(self, tmp_path: Path):
        """Test that duplicate port IDs are caught."""
        circuit = [
            {"type": "source_component", "source_component_id": "comp_1", "name": "R1"},
            {"type": "source_port", "source_port_id": "port_1", "source_component_id": "comp_1", "name": "1"},
            {"type": "source_port", "source_port_id": "port_1", "source_component_id": "comp_1", "name": "2"},
        ]
        file_path = tmp_path / "dup_port.json"
        file_path.write_text(json.dumps(circuit))

        result = validate_circuit_file(file_path)

        assert not result.is_valid
        assert any("Duplicate" in str(e) for e in result.errors)


class TestSourceReferences:
    """Tests for source reference validation."""

    def test_invalid_port_component_ref(self, tmp_path: Path):
        """Test that port referencing non-existent component is caught."""
        circuit = [
            {"type": "source_port", "source_port_id": "port_1", "source_component_id": "nonexistent", "name": "1"},
        ]
        file_path = tmp_path / "bad_ref.json"
        file_path.write_text(json.dumps(circuit))

        result = validate_circuit_file(file_path)

        assert not result.is_valid
        assert any("non-existent" in str(e) for e in result.errors)

    def test_invalid_trace_port_ref(self, tmp_path: Path):
        """Test that trace referencing non-existent port is caught."""
        circuit = [
            {"type": "source_component", "source_component_id": "comp_1", "name": "R1"},
            {
                "type": "source_trace",
                "source_trace_id": "trace_1",
                "connected_source_port_ids": ["nonexistent_port"],
                "connected_source_net_ids": [],
            },
        ]
        file_path = tmp_path / "bad_trace.json"
        file_path.write_text(json.dumps(circuit))

        result = validate_circuit_file(file_path)

        assert not result.is_valid
        assert any("non-existent" in str(e) for e in result.errors)

    def test_invalid_trace_net_ref(self, tmp_path: Path):
        """Test that trace referencing non-existent net is caught."""
        circuit = [
            {"type": "source_component", "source_component_id": "comp_1", "name": "R1"},
            {"type": "source_port", "source_port_id": "port_1", "source_component_id": "comp_1", "name": "1"},
            {
                "type": "source_trace",
                "source_trace_id": "trace_1",
                "connected_source_port_ids": ["port_1"],
                "connected_source_net_ids": ["nonexistent_net"],
            },
        ]
        file_path = tmp_path / "bad_net.json"
        file_path.write_text(json.dumps(circuit))

        result = validate_circuit_file(file_path)

        assert not result.is_valid
        assert any("non-existent" in str(e) for e in result.errors)


class TestTraceConnections:
    """Tests for trace connection validation."""

    def test_trace_without_ports(self, tmp_path: Path):
        """Test that trace without ports is caught."""
        circuit = [
            {"type": "source_net", "source_net_id": "net_1", "name": "VCC"},
            {
                "type": "source_trace",
                "source_trace_id": "trace_1",
                "connected_source_port_ids": [],
                "connected_source_net_ids": ["net_1"],
            },
        ]
        file_path = tmp_path / "no_ports.json"
        file_path.write_text(json.dumps(circuit))

        result = validate_circuit_file(file_path)

        assert not result.is_valid
        assert any("no connected ports" in str(e).lower() for e in result.errors)

    def test_trace_single_port_warning(self, tmp_path: Path):
        """Test that trace with only one port and no net warns."""
        circuit = [
            {"type": "source_component", "source_component_id": "comp_1", "name": "R1"},
            {"type": "source_port", "source_port_id": "port_1", "source_component_id": "comp_1", "name": "1"},
            {
                "type": "source_trace",
                "source_trace_id": "trace_1",
                "connected_source_port_ids": ["port_1"],
                "connected_source_net_ids": [],
            },
        ]
        file_path = tmp_path / "single_port.json"
        file_path.write_text(json.dumps(circuit))

        result = validate_circuit_file(file_path)

        # Should have warning about floating connection
        assert any("floating" in str(w).lower() for w in result.warnings)

    def test_valid_two_port_trace(self, tmp_path: Path):
        """Test that trace connecting two ports is valid."""
        circuit = [
            {"type": "source_component", "source_component_id": "comp_1", "name": "R1"},
            {"type": "source_component", "source_component_id": "comp_2", "name": "R2"},
            {"type": "source_port", "source_port_id": "port_1", "source_component_id": "comp_1", "name": "1"},
            {"type": "source_port", "source_port_id": "port_2", "source_component_id": "comp_2", "name": "1"},
            {
                "type": "source_trace",
                "source_trace_id": "trace_1",
                "connected_source_port_ids": ["port_1", "port_2"],
                "connected_source_net_ids": [],
            },
        ]
        file_path = tmp_path / "two_ports.json"
        file_path.write_text(json.dumps(circuit))

        result = validate_circuit_file(file_path)

        assert result.is_valid


class TestSourceGroup:
    """Tests for source_group validation."""

    def test_valid_group(self, tmp_path: Path):
        """Test that valid source_group is accepted."""
        circuit = [
            {"type": "source_group", "source_group_id": "group_1", "name": "Power Supply", "subcircuit_id": "power"},
            {"type": "source_component", "source_component_id": "comp_1", "name": "U1", "subcircuit_id": "power"},
        ]
        file_path = tmp_path / "group.json"
        file_path.write_text(json.dumps(circuit))

        result = validate_circuit_file(file_path)

        assert result.is_valid

    def test_invalid_parent_group_ref(self, tmp_path: Path):
        """Test that invalid parent_source_group_id is caught."""
        circuit = [
            {"type": "source_group", "source_group_id": "group_1", "name": "Sub", "parent_source_group_id": "nonexistent"},
        ]
        file_path = tmp_path / "bad_parent.json"
        file_path.write_text(json.dumps(circuit))

        result = validate_circuit_file(file_path)

        assert not result.is_valid
        assert any("non-existent" in str(e) for e in result.errors)
