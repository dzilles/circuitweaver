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
    """A simple valid LED circuit (logic-only)."""
    return [
        {
            "type": "source_component",
            "source_component_id": "src_r1",
            "name": "R1",
            "ftype": "simple_resistor",
            "resistance": 330,
            "footprint": "Resistor_SMD:R_0603_1608Metric",
        },
        {
            "type": "source_component",
            "source_component_id": "src_led1",
            "name": "LED1",
            "ftype": "simple_led",
            "color": "red",
            "footprint": "LED_SMD:LED_0603_1608Metric",
        },
        {
            "type": "source_port",
            "source_port_id": "port_r1_1",
            "source_component_id": "src_r1",
            "name": "1",
        },
        {
            "type": "source_port",
            "source_port_id": "port_r1_2",
            "source_component_id": "src_r1",
            "name": "2",
        },
        {
            "type": "source_port",
            "source_port_id": "port_led1_a",
            "source_component_id": "src_led1",
            "name": "A",
        },
        {
            "type": "source_port",
            "source_port_id": "port_led1_k",
            "source_component_id": "src_led1",
            "name": "K",
        },
        {
            "type": "source_trace",
            "source_trace_id": "trace_1",
            "connected_source_port_ids": ["port_r1_2", "port_led1_a"],
        },
    ]


@pytest.fixture
def diagonal_trace_circuit() -> list[dict]:
    """A circuit with an invalid connection (stub)."""
    return [
        {
            "type": "source_component",
            "source_component_id": "src_r1",
            "name": "R1",
            "ftype": "simple_resistor",
            "resistance": 10000,
        },
        {
            "type": "source_port",
            "source_port_id": "port_r1_1",
            "source_component_id": "src_r1",
            "name": "1",
        },
        {
            "type": "source_trace",
            "source_trace_id": "trace_stub",
            "connected_source_port_ids": ["port_r1_1"],
            "connected_source_net_ids": [],
        },
    ]


@pytest.fixture
def missing_source_circuit() -> list[dict]:
    """A circuit with source_port referencing non-existent component."""
    return [
        {
            "type": "source_port",
            "source_port_id": "port_r1_1",
            "source_component_id": "src_r1",  # This doesn't exist!
            "name": "1",
        },
    ]


@pytest.fixture
def tmp_circuit_file(tmp_path: Path, simple_led_circuit: list[dict]) -> Path:
    """Create a temporary circuit JSON file."""
    file_path = tmp_path / "circuit.json"
    file_path.write_text(json.dumps(simple_led_circuit, indent=2))
    return file_path
