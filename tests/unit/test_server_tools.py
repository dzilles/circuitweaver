"""Unit tests for MCP server tools."""

import json
from pathlib import Path
import pytest
from circuitweaver.server.tool_registry import validate_circuit_json, search_kicad_parts

@pytest.mark.asyncio
async def test_validate_tool_success(tmp_path: Path):
    """Test the validate_circuit_json tool with a valid file."""
    circuit = [
        {"type": "source_component", "source_component_id": "r1", "name": "R1"}
    ]
    file_path = tmp_path / "valid.json"
    file_path.write_text(json.dumps(circuit))
    
    result = await validate_circuit_json(str(file_path))
    assert "SUCCESS" in result
    assert "is valid" in result

@pytest.mark.asyncio
async def test_validate_tool_failure(tmp_path: Path):
    """Test the validate_circuit_json tool with an invalid file."""
    circuit = [
        {"type": "source_port", "source_port_id": "p1", "source_component_id": "non_existent", "name": "1"}
    ]
    file_path = tmp_path / "invalid.json"
    file_path.write_text(json.dumps(circuit))
    
    result = await validate_circuit_json(str(file_path))
    assert "FAILED" in result
    assert "non-existent source_component" in result

@pytest.mark.asyncio
async def test_search_parts_tool():
    """Test the search_kicad_parts tool."""
    # This might depend on KiCad libraries being present on the system.
    # If not present, it should at least return "No results found" rather than crashing.
    result = await search_kicad_parts("resistor")
    assert isinstance(result, str)
    # Even if no libraries are found, it should be a graceful message
    assert "Found" in result or "No results found" in result
