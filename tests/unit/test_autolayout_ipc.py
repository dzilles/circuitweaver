import json
import pytest
from pathlib import Path
from circuitweaver.compiler.autolayout import AutoLayoutEngine
from circuitweaver.types.circuit_json import SourceComponent

def test_autolayout_node_check():
    """Test that AutoLayoutEngine raises RuntimeError if node is missing."""
    import shutil
    original_which = shutil.which
    
    def mock_which(cmd):
        if cmd == "node": return None
        return original_which(cmd)
    
    shutil.which = mock_which
    try:
        with pytest.raises(RuntimeError, match="Node.js is required"):
            AutoLayoutEngine()
    finally:
        shutil.which = original_which

def test_autolayout_basic_ipc():
    """Test basic IPC with node (requires node and elkjs in node_modules)."""
    # Verify node_modules/elkjs exists as it is required for layout_helper.js
    if not (Path.cwd() / "node_modules" / "elkjs").exists():
        pytest.skip("elkjs not found in node_modules")
        
    engine = AutoLayoutEngine()
    
    # Minimal elements for a layout
    elements = [
        SourceComponent(source_component_id="R1", name="R1", symbol_id="Device:R", ftype="simple_resistor")
    ]
    
    try:
        results = engine.layout(elements)
        # Check if we got schematic elements back
        schematic_comps = [e for e in results if e.type == "schematic_component"]
        assert len(schematic_comps) == 1
        assert schematic_comps[0].source_component_id == "R1"
        assert hasattr(schematic_comps[0].center, 'x')
    except Exception as e:
        pytest.fail(f"Layout failed: {e}")
