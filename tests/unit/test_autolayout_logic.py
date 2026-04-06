import pytest
from circuitweaver.compiler.layout.engine import AutoLayoutEngine
from circuitweaver.compiler.layout.registry import LayoutContext, MappingRegistry
from circuitweaver.compiler.layout.models import LayoutNode
from circuitweaver.compiler.layout.plugins.elk_layered import ElkLayeredPlugin, ElkSizingConfig
from circuitweaver.types.circuit_json import SourceComponent, SourcePort, SourceGroup, SourceNet, SourceTrace, Point, SchematicHierarchicalPin, GridOffset
from circuitweaver.library.pinout import SymbolInfo, PinInfo

@pytest.fixture
def engine():
    return AutoLayoutEngine()

@pytest.fixture
def plugin():
    return ElkLayeredPlugin()

@pytest.fixture
def mock_symbol_map():
    resistor_sym = SymbolInfo(
        symbol_id="Device:R",
        name="R",
        pins=[
            PinInfo(number="1", name="~", grid_offset=GridOffset(x=0, y=0), direction="left", electrical_type="passive"),
            PinInfo(number="2", name="~", grid_offset=GridOffset(x=0, y=10), direction="right", electrical_type="passive")
        ],
        bounding_box_min=GridOffset(x=-5, y=0),
        bounding_box_max=GridOffset(x=5, y=10)
    )
    return {"Device:R": resistor_sym}

def test_build_elk_component_node(plugin, mock_symbol_map):
    comp = SourceComponent(source_component_id="R1", name="R1", symbol_id="Device:R")
    ports = [
        SourcePort(source_port_id="p1", source_component_id="R1", name="1", pin_number=1),
        SourcePort(source_port_id="p2", source_component_id="R1", name="2", pin_number=2)
    ]
    
    context = LayoutContext(
        sheet_id="root",
        elements=[comp] + ports,
        root_node=LayoutNode(id="root"),
        registry=MappingRegistry(),
        symbol_map=mock_symbol_map
    )
    
    plugin._add_component_node(comp, context)
    
    assert len(context.root_node.children) == 1
    node = context.root_node.children[0]
    assert node.id == "R1"
    assert len(node.ports) == 2
    assert node.width == 10
    assert node.height == 10

def test_build_elk_box_node(plugin):
    group = SourceGroup(source_group_id="G1", name="Subcircuit", is_subcircuit=True)
    hpin = SchematicHierarchicalPin(
        schematic_hierarchical_pin_id="hpin1",
        sheet_id="root",
        source_net_id="N1",
        schematic_box_id="box_G1",
        center=Point(x=0, y=0),
        text="IN"
    )
    
    context = LayoutContext(
        sheet_id="root",
        elements=[group, hpin],
        root_node=LayoutNode(id="root"),
        registry=MappingRegistry(),
        symbol_map={}
    )
    
    plugin._add_box_node(group, context)
    
    assert len(context.root_node.children) == 1 # 1 for node
    node = context.root_node.children[0]
    assert node.id == "box_G1"
    
    # Check that it has children for name/body/file in root sheet
    assert len(node.children) == 3
    assert any(c.id == "inner_body_box_G1" for c in node.children)
    inner = next(c for c in node.children if c.id == "inner_body_box_G1")
    assert len(inner.ports) == 1

def test_build_elk_connectivity_edges(plugin):
    connectivity = {
        "root": [{
            "trace_id": "T1",
            "net_id": "N1",
            "ports": ["p1", "p2"],
            "is_inter_group": False,
            "is_inter_sheet": False,
            "hpin_id": None
        }]
    }
    
    context = LayoutContext(
        sheet_id="root",
        elements=[],
        root_node=LayoutNode(id="root"),
        registry=MappingRegistry(),
        symbol_map={},
        sheet_connectivity=connectivity
    )
    
    context.registry.element_to_port["p1"] = "R1:1"
    context.registry.element_to_port["p2"] = "R2:1"
    
    plugin._build_connectivity(context)
    
    edges = context.root_node.edges
    assert len(edges) == 1
    assert edges[0].sources == ["R1:1"]
    assert edges[0].targets == ["R2:1"]