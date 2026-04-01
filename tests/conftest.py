"""Pytest configuration and fixtures."""

import json
from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    """Return path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def valid_fixtures_dir(fixtures_dir: Path) -> Path:
    """Return path to valid circuit fixtures."""
    return fixtures_dir / "valid"


@pytest.fixture
def invalid_fixtures_dir(fixtures_dir: Path) -> Path:
    """Return path to invalid circuit fixtures."""
    return fixtures_dir / "invalid"


@pytest.fixture
def simple_led_circuit() -> list[dict]:
    """A simple valid LED circuit."""
    return [
        {
            "type": "source_component",
            "source_component_id": "src_r1",
            "name": "R1",
            "value": "330",
            "footprint": "Resistor_SMD:R_0603_1608Metric",
        },
        {
            "type": "source_component",
            "source_component_id": "src_led1",
            "name": "LED1",
            "value": "Red",
            "footprint": "LED_SMD:LED_0603_1608Metric",
        },
        {
            "type": "schematic_component",
            "schematic_component_id": "sch_r1",
            "source_component_id": "src_r1",
            "center": {"x": 20, "y": 20},
            "rotation": 0,
        },
        {
            "type": "schematic_component",
            "schematic_component_id": "sch_led1",
            "source_component_id": "src_led1",
            "center": {"x": 30, "y": 20},
            "rotation": 0,
        },
        {
            "type": "schematic_trace",
            "schematic_trace_id": "trace_1",
            "edges": [{"from": {"x": 22, "y": 20}, "to": {"x": 28, "y": 20}}],
        },
    ]


@pytest.fixture
def diagonal_trace_circuit() -> list[dict]:
    """A circuit with an invalid diagonal trace."""
    return [
        {
            "type": "source_component",
            "source_component_id": "src_r1",
            "name": "R1",
            "value": "10k",
        },
        {
            "type": "schematic_component",
            "schematic_component_id": "sch_r1",
            "source_component_id": "src_r1",
            "center": {"x": 10, "y": 10},
            "rotation": 0,
        },
        {
            "type": "schematic_trace",
            "schematic_trace_id": "trace_bad",
            "edges": [
                # This is diagonal - both x and y change!
                {"from": {"x": 10, "y": 10}, "to": {"x": 20, "y": 20}}
            ],
        },
    ]


@pytest.fixture
def missing_source_circuit() -> list[dict]:
    """A circuit with schematic_component referencing non-existent source."""
    return [
        {
            "type": "schematic_component",
            "schematic_component_id": "sch_r1",
            "source_component_id": "src_r1",  # This doesn't exist!
            "center": {"x": 10, "y": 10},
            "rotation": 0,
        },
    ]


@pytest.fixture
def tmp_circuit_file(tmp_path: Path, simple_led_circuit: list[dict]) -> Path:
    """Create a temporary circuit JSON file."""
    file_path = tmp_path / "circuit.json"
    file_path.write_text(json.dumps(simple_led_circuit, indent=2))
    return file_path
