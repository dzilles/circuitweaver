import pytest
from circuitweaver.compiler.autolayout import AutoLayoutEngine, ElkSizingConfig
from circuitweaver.types.circuit_json import SourceComponent, SourcePort, SourceGroup, SourceNet, SourceTrace, Point, SchematicHierarchicalPin
from circuitweaver.library.pinout import SymbolInfo, GridOffset, PinInfo

@pytest.fixture
def engine():
    return AutoLayoutEngine()

@pytest.fixture
def mock_symbol_map():
    # Simple resistor-like symbol
    resistor_sym = SymbolInfo(
        symbol_id="Device:R",
        name="R",
        pins=[
            PinInfo(number="1", name="~", grid_offset=GridOffset(0, 0), direction="left", electrical_type="passive"),
            PinInfo(number="2", name="~", grid_offset=GridOffset(0, 10), direction="right", electrical_type="passive")
        ],
        bounding_box_min=GridOffset(-5, 0),
        bounding_box_max=GridOffset(5, 10)
    )
    return {"Device:R": resistor_sym}

def test_build_elk_component_node(engine, mock_symbol_map):
    comp = SourceComponent(source_component_id="R1", name="R1", symbol_id="Device:R")
    ports = [
        SourcePort(source_port_id="p1", source_component_id="R1", name="1", pin_number=1),
        SourcePort(source_port_id="p2", source_component_id="R1", name="2", pin_number=2),
    ]
    
    node, edges = engine._build_elk_component_node(comp, ports, [], set(), mock_symbol_map)
    
    assert node["id"] == "R1"
    assert node["width"] == 10  # max(5 - (-5), 10)
    assert node["height"] == 10 # max(10 - 0, 10)
    assert len(node["ports"]) == 2
    
    # Check port 1 (left -> EAST in ELK)
    p1 = next(p for p in node["ports"] if p["id"] == "R1:p1")
    assert p1["layoutOptions"]["org.eclipse.elk.port.side"] == "EAST"
    # x = pi.x - min.x = 0 - (-5) = 5
    # y = pi.y - min.y = 0 - 0 = 0
    assert p1["x"] == 5
    assert p1["y"] == 0

def test_build_elk_box_node(engine):
    group = SourceGroup(source_group_id="G1", name="Subcircuit", is_subcircuit=True)
    hpin = SchematicHierarchicalPin(
        schematic_hierarchical_pin_id="hpin1",
        sheet_id="root",
        source_net_id="N1",
        schematic_box_id="box_G1",
        center=Point(x=0, y=0),
        text="IN"
    )
    
    node, edges = engine._build_elk_box_node(group, "root", [], set(), [hpin])
    
    assert node["id"] == "box_G1"
    # Should contain children for name and file in root sheet
    assert "children" in node
    inner_body = next(c for c in node["children"] if c["id"] == "inner_body_box_G1")
    assert len(inner_body["ports"]) == 1
    assert inner_body["ports"][0]["id"] == "box_G1:hpin1"

def test_build_elk_connectivity_edges(engine):
    connectivity = [{
        "trace_id": "T1",
        "net_id": "N1",
        "ports": ["p1", "p2"],
        "is_inter_group": False,
        "is_inter_sheet": False,
        "hpin_id": None
    }]
    components = [
        SourceComponent(source_component_id="R1", name="R1"),
        SourceComponent(source_component_id="R2", name="R2")
    ]
    ports_by_comp = {
        "R1": [SourcePort(source_port_id="p1", source_component_id="R1", name="1")],
        "R2": [SourcePort(source_port_id="p2", source_component_id="R2", name="1")]
    }
    
    edges = engine._build_elk_connectivity_edges(connectivity, components, [], ports_by_comp, [])
    
    assert len(edges) == 1
    assert edges[0]["sources"] == ["R1:p1"]
    assert edges[0]["targets"] == ["R2:p2"]
