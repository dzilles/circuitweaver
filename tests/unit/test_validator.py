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

    def test_diagonal_trace(self, tmp_path: Path, diagonal_trace_circuit: list[dict]):
        """Test that diagonal traces are caught."""
        file_path = tmp_path / "diagonal.json"
        file_path.write_text(json.dumps(diagonal_trace_circuit))

        result = validate_circuit_file(file_path)

        assert not result.is_valid
        assert any("diagonal" in str(e).lower() for e in result.errors)

    def test_missing_source_component(
        self, tmp_path: Path, missing_source_circuit: list[dict]
    ):
        """Test that missing source_component reference is caught."""
        file_path = tmp_path / "missing_source.json"
        file_path.write_text(json.dumps(missing_source_circuit))

        result = validate_circuit_file(file_path)

        assert not result.is_valid
        assert any("non-existent" in str(e) for e in result.errors)

    def test_file_not_found(self, tmp_path: Path):
        """Test that missing file is handled."""
        file_path = tmp_path / "nonexistent.json"

        result = validate_circuit_file(file_path)

        assert not result.is_valid
        assert any("not found" in str(e).lower() for e in result.errors)


class TestOrthogonalTraces:
    """Tests for orthogonal trace validation."""

    def test_horizontal_trace_valid(self, tmp_path: Path):
        """Test that horizontal traces are valid."""
        circuit = [
            {
                "type": "schematic_trace",
                "schematic_trace_id": "trace_h",
                "edges": [{"from": {"x": 10, "y": 20}, "to": {"x": 30, "y": 20}}],
            }
        ]
        file_path = tmp_path / "horizontal.json"
        file_path.write_text(json.dumps(circuit))

        result = validate_circuit_file(file_path)

        # Should not have orthogonal errors
        orthogonal_errors = [e for e in result.errors if "orthogonal" in str(e).lower()]
        assert len(orthogonal_errors) == 0

    def test_vertical_trace_valid(self, tmp_path: Path):
        """Test that vertical traces are valid."""
        circuit = [
            {
                "type": "schematic_trace",
                "schematic_trace_id": "trace_v",
                "edges": [{"from": {"x": 10, "y": 20}, "to": {"x": 10, "y": 40}}],
            }
        ]
        file_path = tmp_path / "vertical.json"
        file_path.write_text(json.dumps(circuit))

        result = validate_circuit_file(file_path)

        orthogonal_errors = [e for e in result.errors if "orthogonal" in str(e).lower()]
        assert len(orthogonal_errors) == 0

    def test_l_shaped_trace_valid(self, tmp_path: Path):
        """Test that L-shaped traces (two orthogonal segments) are valid."""
        circuit = [
            {
                "type": "schematic_trace",
                "schematic_trace_id": "trace_l",
                "edges": [
                    {"from": {"x": 10, "y": 10}, "to": {"x": 20, "y": 10}},
                    {"from": {"x": 20, "y": 10}, "to": {"x": 20, "y": 30}},
                ],
            }
        ]
        file_path = tmp_path / "l_shaped.json"
        file_path.write_text(json.dumps(circuit))

        result = validate_circuit_file(file_path)

        orthogonal_errors = [e for e in result.errors if "orthogonal" in str(e).lower()]
        assert len(orthogonal_errors) == 0


class TestSourceFirstRule:
    """Tests for source-first ordering rule."""

    def test_source_before_schematic_valid(self, tmp_path: Path):
        """Test that source before schematic is valid."""
        circuit = [
            {
                "type": "source_component",
                "source_component_id": "src_r1",
                "name": "R1",
            },
            {
                "type": "schematic_component",
                "schematic_component_id": "sch_r1",
                "source_component_id": "src_r1",
                "center": {"x": 10, "y": 10},
                "rotation": 0,
            },
        ]
        file_path = tmp_path / "source_first.json"
        file_path.write_text(json.dumps(circuit))

        result = validate_circuit_file(file_path)

        source_errors = [e for e in result.errors if "source_first" in str(e)]
        assert len(source_errors) == 0

    def test_schematic_before_source_invalid(self, tmp_path: Path):
        """Test that schematic before source is invalid."""
        circuit = [
            {
                "type": "schematic_component",
                "schematic_component_id": "sch_r1",
                "source_component_id": "src_r1",
                "center": {"x": 10, "y": 10},
                "rotation": 0,
            },
            {
                "type": "source_component",
                "source_component_id": "src_r1",
                "name": "R1",
            },
        ]
        file_path = tmp_path / "schematic_first.json"
        file_path.write_text(json.dumps(circuit))

        result = validate_circuit_file(file_path)

        assert not result.is_valid
        assert any("AFTER" in str(e) for e in result.errors)
