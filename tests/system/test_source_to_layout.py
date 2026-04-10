"""System tests for Source to Layout transformation.

These tests verify the complete transformation of realistic circuit designs
from Source elements (logical netlist) to Layout elements (ELK graph format).
"""

import pytest

from circuitweaver.transform import (
    SourceToLayoutTransform,
    LayoutRegistry,
    get_effective_symbol_id,
)
from circuitweaver.types import (
    SourceComponent,
    SourcePort,
    SourceNet,
    SourceTrace,
    SourceGroup,
    LayoutNode,
    LayoutPort,
    LayoutEdge,
    SchematicNetLabel,
    SchematicHierarchicalPin,
    SchematicHierarchicalLabel,
    SchematicNoConnect,
)


# =============================================================================
# Fixtures: Realistic Circuit Scenarios
# =============================================================================


@pytest.fixture
def simple_resistor_circuit():
    """A simple voltage divider circuit with two resistors."""
    return [
        SourceComponent(source_component_id="R1", name="R1", ftype="simple_resistor"),
        SourcePort(source_port_id="R1_1", source_component_id="R1", name="1", pin_number=1),
        SourcePort(source_port_id="R1_2", source_component_id="R1", name="2", pin_number=2),
        SourceComponent(source_component_id="R2", name="R2", ftype="simple_resistor"),
        SourcePort(source_port_id="R2_1", source_component_id="R2", name="1", pin_number=1),
        SourcePort(source_port_id="R2_2", source_component_id="R2", name="2", pin_number=2),
        SourceNet(source_net_id="net_vcc", name="VCC", is_power=True),
        SourceNet(source_net_id="net_gnd", name="GND", is_ground=True),
        SourceNet(source_net_id="net_mid", name="MID"),
        SourceTrace(
            source_trace_id="trace_vcc",
            connected_source_port_ids=["R1_1"],
            connected_source_net_ids=["net_vcc"],
        ),
        SourceTrace(
            source_trace_id="trace_mid",
            connected_source_port_ids=["R1_2", "R2_1"],
            connected_source_net_ids=["net_mid"],
        ),
        SourceTrace(
            source_trace_id="trace_gnd",
            connected_source_port_ids=["R2_2"],
            connected_source_net_ids=["net_gnd"],
        ),
    ]


@pytest.fixture
def led_circuit():
    """LED circuit with resistor and power supply."""
    return [
        SourceComponent(source_component_id="R1", name="R1", ftype="simple_resistor"),
        SourcePort(source_port_id="R1_1", source_component_id="R1", name="1", pin_number=1),
        SourcePort(source_port_id="R1_2", source_component_id="R1", name="2", pin_number=2),
        SourceComponent(source_component_id="LED1", name="LED1", ftype="simple_led"),
        SourcePort(source_port_id="LED1_A", source_component_id="LED1", name="A", pin_number=1),
        SourcePort(source_port_id="LED1_K", source_component_id="LED1", name="K", pin_number=2),
        SourceNet(source_net_id="net_vcc", name="VCC", is_power=True),
        SourceNet(source_net_id="net_gnd", name="GND", is_ground=True),
        SourceTrace(
            source_trace_id="trace_vcc",
            connected_source_port_ids=["R1_1"],
            connected_source_net_ids=["net_vcc"],
        ),
        SourceTrace(
            source_trace_id="trace_led",
            connected_source_port_ids=["R1_2", "LED1_A"],
        ),
        SourceTrace(
            source_trace_id="trace_gnd",
            connected_source_port_ids=["LED1_K"],
            connected_source_net_ids=["net_gnd"],
        ),
    ]


@pytest.fixture
def rc_filter_circuit():
    """RC low-pass filter circuit."""
    return [
        SourceComponent(source_component_id="R1", name="R1", ftype="simple_resistor"),
        SourcePort(source_port_id="R1_1", source_component_id="R1", name="1", pin_number=1),
        SourcePort(source_port_id="R1_2", source_component_id="R1", name="2", pin_number=2),
        SourceComponent(source_component_id="C1", name="C1", ftype="simple_capacitor"),
        SourcePort(source_port_id="C1_1", source_component_id="C1", name="1", pin_number=1),
        SourcePort(source_port_id="C1_2", source_component_id="C1", name="2", pin_number=2),
        SourceNet(source_net_id="net_in", name="IN", is_analog_signal=True),
        SourceNet(source_net_id="net_out", name="OUT", is_analog_signal=True),
        SourceNet(source_net_id="net_gnd", name="GND", is_ground=True),
        SourceTrace(
            source_trace_id="trace_in",
            connected_source_port_ids=["R1_1"],
            connected_source_net_ids=["net_in"],
        ),
        SourceTrace(
            source_trace_id="trace_rc",
            connected_source_port_ids=["R1_2", "C1_1"],
            connected_source_net_ids=["net_out"],
        ),
        SourceTrace(
            source_trace_id="trace_gnd",
            connected_source_port_ids=["C1_2"],
            connected_source_net_ids=["net_gnd"],
        ),
    ]


@pytest.fixture
def multi_component_circuit():
    """Circuit with multiple component types."""
    return [
        SourceComponent(source_component_id="R1", name="R1", ftype="simple_resistor"),
        SourcePort(source_port_id="R1_1", source_component_id="R1", name="1", pin_number=1),
        SourcePort(source_port_id="R1_2", source_component_id="R1", name="2", pin_number=2),
        SourceComponent(source_component_id="C1", name="C1", ftype="simple_capacitor"),
        SourcePort(source_port_id="C1_1", source_component_id="C1", name="1", pin_number=1),
        SourcePort(source_port_id="C1_2", source_component_id="C1", name="2", pin_number=2),
        SourceComponent(source_component_id="LED1", name="LED1", ftype="simple_led"),
        SourcePort(source_port_id="LED1_A", source_component_id="LED1", name="A", pin_number=1),
        SourcePort(source_port_id="LED1_K", source_component_id="LED1", name="K", pin_number=2),
        SourceComponent(source_component_id="D1", name="D1", ftype="simple_diode"),
        SourcePort(source_port_id="D1_A", source_component_id="D1", name="A", pin_number=1),
        SourcePort(source_port_id="D1_K", source_component_id="D1", name="K", pin_number=2),
    ]


@pytest.fixture
def hierarchical_circuit():
    """Circuit with hierarchical subcircuit (group with is_subcircuit=True)."""
    from circuitweaver.types import Point

    return [
        # Root level components
        SourceComponent(source_component_id="R1", name="R1", ftype="simple_resistor"),
        SourcePort(source_port_id="R1_1", source_component_id="R1", name="1", pin_number=1),
        SourcePort(source_port_id="R1_2", source_component_id="R1", name="2", pin_number=2),
        # Subcircuit group
        SourceGroup(
            source_group_id="power_supply",
            name="Power Supply",
            is_subcircuit=True,
        ),
        # Hierarchical pins on the box (center will be updated by layout engine)
        SchematicHierarchicalPin(
            schematic_hierarchical_pin_id="hpin_vout",
            source_net_id="net_vout",
            schematic_box_id="box_power_supply",
            center=Point(x=0, y=0),
            text="VOUT",
            sheet_id="root",
        ),
        SchematicHierarchicalPin(
            schematic_hierarchical_pin_id="hpin_gnd",
            source_net_id="net_gnd",
            schematic_box_id="box_power_supply",
            center=Point(x=0, y=0),
            text="GND",
            sheet_id="root",
        ),
    ]


@pytest.fixture
def circuit_with_net_labels():
    """Circuit with net labels attached to ports."""
    from circuitweaver.types import Point

    return [
        SourceComponent(source_component_id="R1", name="R1", ftype="simple_resistor"),
        SourcePort(
            source_port_id="R1_1", source_component_id="R1", name="1", pin_number=1
        ),
        SourcePort(
            source_port_id="R1_2", source_component_id="R1", name="2", pin_number=2
        ),
        SourceNet(source_net_id="net_vcc", name="VCC", is_power=True),
        SchematicNetLabel(
            schematic_net_label_id="label_vcc",
            source_net_id="net_vcc",
            source_port_id="R1_1",
            center=Point(x=0, y=0),  # Position will be updated by layout engine
            text="VCC",
            anchor_side="left",
            sheet_id="root",
        ),
    ]


@pytest.fixture
def circuit_with_no_connects():
    """Circuit with no-connect markers on unused pins."""
    return [
        SourceComponent(
            source_component_id="U1",
            name="U1",
            symbol_id="Device:Generic_IC",
        ),
        SourcePort(
            source_port_id="U1_1",
            source_component_id="U1",
            name="1",
            pin_number=1,
        ),
        SourcePort(
            source_port_id="U1_2",
            source_component_id="U1",
            name="2",
            pin_number=2,
            do_not_connect=True,
        ),
        SourcePort(
            source_port_id="U1_3",
            source_component_id="U1",
            name="3",
            pin_number=3,
        ),
        SchematicNoConnect(
            schematic_no_connect_id="nc_1",
            schematic_port_id="port_U1_2",
            position=None,
            sheet_id="root",
        ),
    ]


# =============================================================================
# Test: Basic Transformation
# =============================================================================


class TestBasicTransformation:
    """Test basic source to layout transformation."""

    def test_empty_circuit(self):
        """Test transforming an empty circuit."""
        transform = SourceToLayoutTransform()
        layout, registry = transform.transform("root", [])

        assert layout.id == "root"
        assert len(layout.children) == 0
        assert len(layout.edges) == 0

    def test_single_component(self):
        """Test transforming a single component."""
        elements = [
            SourceComponent(source_component_id="R1", name="R1", ftype="simple_resistor")
        ]
        transform = SourceToLayoutTransform()
        layout, registry = transform.transform("root", elements)

        assert len(layout.children) == 1
        node = layout.children[0]
        assert node.id == "R1"
        assert node.width > 0
        assert node.height > 0

    def test_root_node_has_elk_algorithm(self):
        """Test that root node has ELK layered algorithm configured."""
        transform = SourceToLayoutTransform()
        layout, _ = transform.transform("test_sheet", [])

        assert "org.eclipse.elk.algorithm" in layout.layoutOptions
        assert layout.layoutOptions["org.eclipse.elk.algorithm"] == "layered"

    def test_root_node_has_padding(self):
        """Test that root node has padding configured."""
        transform = SourceToLayoutTransform()
        layout, _ = transform.transform("root", [])

        assert "org.eclipse.elk.padding" in layout.layoutOptions


# =============================================================================
# Test: Component Node Creation
# =============================================================================


class TestComponentNodeCreation:
    """Test component node creation in layout graph."""

    def test_components_become_child_nodes(self, simple_resistor_circuit):
        """Test that source components become child nodes."""
        transform = SourceToLayoutTransform()
        layout, _ = transform.transform("root", simple_resistor_circuit)

        component_count = sum(
            1 for e in simple_resistor_circuit if isinstance(e, SourceComponent)
        )
        # Filter to only component nodes (not boxes or labels)
        component_nodes = [
            c for c in layout.children if not c.id.startswith(("box_", "label_", "nc_"))
        ]
        assert len(component_nodes) == component_count

    def test_component_ids_are_preserved(self, simple_resistor_circuit):
        """Test that component IDs are used as node IDs."""
        transform = SourceToLayoutTransform()
        layout, _ = transform.transform("root", simple_resistor_circuit)

        node_ids = {c.id for c in layout.children}
        assert "R1" in node_ids
        assert "R2" in node_ids

    def test_component_has_fixed_port_constraints(self, simple_resistor_circuit):
        """Test that component nodes have fixed port constraints."""
        transform = SourceToLayoutTransform()
        layout, _ = transform.transform("root", simple_resistor_circuit)

        for child in layout.children:
            if child.id in ("R1", "R2"):
                assert "org.eclipse.elk.portConstraints" in child.layoutOptions
                assert child.layoutOptions["org.eclipse.elk.portConstraints"] == "FIXED_POS"

    def test_multi_component_types(self, multi_component_circuit):
        """Test circuit with multiple component types."""
        transform = SourceToLayoutTransform()
        layout, registry = transform.transform("root", multi_component_circuit)

        component_nodes = [
            c for c in layout.children if not c.id.startswith(("box_", "label_", "nc_"))
        ]
        assert len(component_nodes) == 4

        node_ids = {c.id for c in component_nodes}
        assert node_ids == {"R1", "C1", "LED1", "D1"}


# =============================================================================
# Test: Registry Tracking
# =============================================================================


class TestRegistryTracking:
    """Test element-to-layout ID tracking via registry."""

    def test_components_registered(self, simple_resistor_circuit):
        """Test that components are registered in the registry."""
        transform = SourceToLayoutTransform()
        _, registry = transform.transform("root", simple_resistor_circuit)

        assert "R1" in registry.element_to_node
        assert "R2" in registry.element_to_node

    def test_reverse_lookup_works(self, simple_resistor_circuit):
        """Test reverse lookup from layout ID to element."""
        transform = SourceToLayoutTransform()
        _, registry = transform.transform("root", simple_resistor_circuit)

        element = registry.get_element_by_layout_id("R1")
        assert element is not None
        assert isinstance(element, SourceComponent)
        assert element.source_component_id == "R1"


# =============================================================================
# Test: Hierarchical Circuits
# =============================================================================


class TestHierarchicalCircuits:
    """Test hierarchical circuit transformation."""

    def test_subcircuit_becomes_box_node(self, hierarchical_circuit):
        """Test that subcircuit groups become box nodes."""
        transform = SourceToLayoutTransform()
        layout, _ = transform.transform("root", hierarchical_circuit)

        # Find box nodes
        box_nodes = [c for c in layout.children if c.id.startswith("box_")]
        assert len(box_nodes) == 1
        assert box_nodes[0].id == "box_power_supply"

    def test_box_has_hierarchical_pins_as_ports(self, hierarchical_circuit):
        """Test that hierarchical pins become ports on box node."""
        transform = SourceToLayoutTransform()
        layout, _ = transform.transform("root", hierarchical_circuit)

        box_node = next(c for c in layout.children if c.id.startswith("box_"))
        assert len(box_node.ports) == 2

        port_ids = {p.id for p in box_node.ports}
        assert "box_power_supply:hpin_vout" in port_ids
        assert "box_power_supply:hpin_gnd" in port_ids

    def test_box_has_minimum_dimensions(self, hierarchical_circuit):
        """Test that box node has minimum dimensions."""
        transform = SourceToLayoutTransform()
        layout, _ = transform.transform("root", hierarchical_circuit)

        box_node = next(c for c in layout.children if c.id.startswith("box_"))
        assert box_node.width >= 250  # MIN_BOX_WIDTH
        assert box_node.height >= 100  # MIN_BOX_HEIGHT

    def test_hierarchical_pins_registered(self, hierarchical_circuit):
        """Test that hierarchical pins are registered in registry."""
        transform = SourceToLayoutTransform()
        _, registry = transform.transform("root", hierarchical_circuit)

        assert "hpin_vout" in registry.element_to_port
        assert "hpin_gnd" in registry.element_to_port


# =============================================================================
# Test: Connectivity
# =============================================================================


class TestConnectivity:
    """Test connectivity (edge) creation from sheet connectivity."""

    def test_connectivity_creates_edges(self):
        """Test that sheet connectivity creates edges."""
        elements = [
            SourceComponent(source_component_id="R1", name="R1", ftype="simple_resistor"),
            SourcePort(source_port_id="R1_1", source_component_id="R1", name="1", pin_number=1),
            SourcePort(source_port_id="R1_2", source_component_id="R1", name="2", pin_number=2),
            SourceComponent(source_component_id="R2", name="R2", ftype="simple_resistor"),
            SourcePort(source_port_id="R2_1", source_component_id="R2", name="1", pin_number=1),
            SourcePort(source_port_id="R2_2", source_component_id="R2", name="2", pin_number=2),
        ]

        # Mock symbol info for port registration
        class MockSymbolInfo:
            width = 40
            height = 40

            class Pin:
                def __init__(self, num, x, y, direction):
                    self.number = str(num)
                    self.direction = direction

                    class Offset:
                        def __init__(self, x, y):
                            self.x = x
                            self.y = y

                    self.grid_offset = Offset(x, y)

            class BBox:
                x = 0
                y = 0

            bounding_box_min = BBox()
            pins = [Pin(1, 0, 20, "left"), Pin(2, 40, 20, "right")]

        symbol_map = {"Device:R": MockSymbolInfo()}

        sheet_connectivity = {
            "root": [
                {
                    "trace_id": "trace_1",
                    "ports": ["R1_2", "R2_1"],
                    "is_inter_group": False,
                }
            ]
        }

        transform = SourceToLayoutTransform(symbol_map=symbol_map)
        layout, registry = transform.transform(
            "root", elements, sheet_connectivity=sheet_connectivity
        )

        # Should have edge connecting R1:2 to R2:1
        assert len(layout.edges) >= 1
        edge = layout.edges[0]
        assert len(edge.sources) == 1
        assert len(edge.targets) == 1


# =============================================================================
# Test: Net Labels
# =============================================================================


class TestNetLabels:
    """Test net label handling."""

    def test_net_labels_without_port_not_added(self, circuit_with_net_labels):
        """Test that net labels without registered port are not added."""
        # Remove SourcePorts so they are NOT registered even by the new fallback
        filtered = [e for e in circuit_with_net_labels if not isinstance(e, SourcePort)]
        
        transform = SourceToLayoutTransform()
        layout, registry = transform.transform("root", filtered)

        # Label should not be in children since no port is registered
        label_nodes = [c for c in layout.children if c.id.startswith("label_")]
        assert len(label_nodes) == 0


# =============================================================================
# Test: No-Connect Markers
# =============================================================================


class TestNoConnectMarkers:
    """Test no-connect marker handling."""

    def test_nc_without_port_not_added(self, circuit_with_no_connects):
        """Test that NC markers without registered port are not added."""
        # Remove SourcePorts so they are NOT registered even by the new fallback
        filtered = [e for e in circuit_with_no_connects if not isinstance(e, SourcePort)]

        transform = SourceToLayoutTransform()
        layout, _ = transform.transform("root", filtered)

        # NC should not be added since port not registered
        nc_nodes = [c for c in layout.children if c.id.startswith("nc_")]
        assert len(nc_nodes) == 0


# =============================================================================
# Test: Realistic Circuit Scenarios
# =============================================================================


class TestRealisticCircuits:
    """Test realistic circuit transformation scenarios."""

    def test_voltage_divider(self, simple_resistor_circuit):
        """Test voltage divider circuit transformation."""
        transform = SourceToLayoutTransform()
        layout, registry = transform.transform("root", simple_resistor_circuit)

        # Should have 2 component nodes
        component_nodes = [
            c for c in layout.children if c.id in ("R1", "R2")
        ]
        assert len(component_nodes) == 2

        # Both should be registered
        assert "R1" in registry.element_to_node
        assert "R2" in registry.element_to_node

    def test_led_circuit(self, led_circuit):
        """Test LED circuit transformation."""
        transform = SourceToLayoutTransform()
        layout, registry = transform.transform("root", led_circuit)

        component_nodes = [
            c for c in layout.children if c.id in ("R1", "LED1")
        ]
        assert len(component_nodes) == 2

    def test_rc_filter(self, rc_filter_circuit):
        """Test RC filter circuit transformation."""
        transform = SourceToLayoutTransform()
        layout, registry = transform.transform("root", rc_filter_circuit)

        component_nodes = [
            c for c in layout.children if c.id in ("R1", "C1")
        ]
        assert len(component_nodes) == 2


# =============================================================================
# Test: Symbol Map Integration
# =============================================================================


class TestSymbolMapIntegration:
    """Test transformation with symbol map for accurate sizing."""

    @pytest.fixture
    def mock_symbol_info(self):
        """Create mock symbol info for a resistor."""

        class PinInfo:
            def __init__(self, number, x, y, direction):
                self.number = str(number)
                self.direction = direction

                class Offset:
                    def __init__(self, x, y):
                        self.x = x
                        self.y = y

                self.grid_offset = Offset(x, y)

        class BBox:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        class SymbolInfo:
            width = 60
            height = 30
            bounding_box_min = BBox(0, 0)
            pins = [
                PinInfo(1, 0, 15, "left"),
                PinInfo(2, 60, 15, "right"),
            ]

        return {"Device:R": SymbolInfo()}

    def test_component_sized_by_symbol_info(self, mock_symbol_info):
        """Test that components are sized according to symbol info."""
        elements = [
            SourceComponent(source_component_id="R1", name="R1", ftype="simple_resistor")
        ]

        transform = SourceToLayoutTransform(symbol_map=mock_symbol_info)
        layout, _ = transform.transform("root", elements)

        node = layout.children[0]
        assert node.width == 60
        assert node.height == 30

    def test_ports_created_from_symbol_pins(self, mock_symbol_info):
        """Test that ports are created from symbol pin info."""
        elements = [
            SourceComponent(source_component_id="R1", name="R1", ftype="simple_resistor"),
            SourcePort(source_port_id="R1_1", source_component_id="R1", name="1", pin_number=1),
            SourcePort(source_port_id="R1_2", source_component_id="R1", name="2", pin_number=2),
        ]

        transform = SourceToLayoutTransform(symbol_map=mock_symbol_info)
        layout, registry = transform.transform("root", elements)

        node = layout.children[0]
        assert len(node.ports) == 2

        port_ids = {p.id for p in node.ports}
        assert "R1:1" in port_ids
        assert "R1:2" in port_ids

    def test_ports_have_correct_positions(self, mock_symbol_info):
        """Test that ports have positions from symbol info."""
        elements = [
            SourceComponent(source_component_id="R1", name="R1", ftype="simple_resistor"),
            SourcePort(source_port_id="R1_1", source_component_id="R1", name="1", pin_number=1),
            SourcePort(source_port_id="R1_2", source_component_id="R1", name="2", pin_number=2),
        ]

        transform = SourceToLayoutTransform(symbol_map=mock_symbol_info)
        layout, _ = transform.transform("root", elements)

        node = layout.children[0]
        port_1 = next(p for p in node.ports if p.id == "R1:1")
        port_2 = next(p for p in node.ports if p.id == "R1:2")

        # Pin 1 at x=0
        assert port_1.x == 0
        # Pin 2 at x=60
        assert port_2.x == 60

    def test_ports_use_absolute_coordinates(self, mock_symbol_info):
        """Test that ports use absolute grid coordinates without ELK side constraints."""
        elements = [
            SourceComponent(source_component_id="R1", name="R1", ftype="simple_resistor"),
            SourcePort(source_port_id="R1_1", source_component_id="R1", name="1", pin_number=1),
            SourcePort(source_port_id="R1_2", source_component_id="R1", name="2", pin_number=2),
        ]

        transform = SourceToLayoutTransform(symbol_map=mock_symbol_info)
        layout, _ = transform.transform("root", elements)

        node = layout.children[0]
        port_1 = next(p for p in node.ports if p.id == "R1:1")
        port_2 = next(p for p in node.ports if p.id == "R1:2")

        # Side constraints should be empty to prevent ELK from overriding our exact coordinates
        assert "org.eclipse.elk.port.side" not in port_1.layoutOptions
        assert "org.eclipse.elk.port.side" not in port_2.layoutOptions
        
        # Verify coordinates are correct relative to bounding box
        assert port_1.x == 0.0
        assert port_1.y == 15.0
        assert port_2.x == 60.0
        assert port_2.y == 15.0

    def test_ports_registered_in_registry(self, mock_symbol_info):
        """Test that ports are registered in the registry."""
        elements = [
            SourceComponent(source_component_id="R1", name="R1", ftype="simple_resistor"),
            SourcePort(source_port_id="R1_1", source_component_id="R1", name="1", pin_number=1),
            SourcePort(source_port_id="R1_2", source_component_id="R1", name="2", pin_number=2),
        ]

        transform = SourceToLayoutTransform(symbol_map=mock_symbol_info)
        _, registry = transform.transform("root", elements)

        assert "R1_1" in registry.element_to_port
        assert "R1_2" in registry.element_to_port


# =============================================================================
# Test: Sheet ID Handling
# =============================================================================


class TestSheetIdHandling:
    """Test sheet ID handling in transformation."""

    def test_different_sheet_ids(self):
        """Test transformation with different sheet IDs."""
        elements = [
            SourceComponent(source_component_id="R1", name="R1", ftype="simple_resistor")
        ]

        transform = SourceToLayoutTransform()

        layout1, _ = transform.transform("root", elements)
        layout2, _ = transform.transform("power_sheet", elements)
        layout3, _ = transform.transform("mcu_sheet", elements)

        assert layout1.id == "root"
        assert layout2.id == "power_sheet"
        assert layout3.id == "mcu_sheet"


# =============================================================================
# Test: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases in transformation."""

    def test_component_without_ports(self):
        """Test component with no matching ports."""
        elements = [
            SourceComponent(source_component_id="R1", name="R1", ftype="simple_resistor")
            # No SourcePort elements
        ]

        transform = SourceToLayoutTransform()
        layout, registry = transform.transform("root", elements)

        # Should still create component node
        assert len(layout.children) == 1
        assert layout.children[0].id == "R1"

    def test_component_with_explicit_symbol_id(self):
        """Test component with explicit symbol_id (not ftype-derived)."""
        elements = [
            SourceComponent(
                source_component_id="U1",
                name="U1",
                symbol_id="Custom:MyIC",
                ftype="custom_ic",
            )
        ]

        transform = SourceToLayoutTransform()
        layout, registry = transform.transform("root", elements)

        assert len(layout.children) == 1
        assert layout.children[0].id == "U1"

    def test_component_without_symbol_info_uses_defaults(self):
        """Test component without symbol info uses default dimensions."""
        elements = [
            SourceComponent(
                source_component_id="U1",
                name="U1",
                symbol_id="Unknown:IC",
            )
        ]

        transform = SourceToLayoutTransform()
        layout, _ = transform.transform("root", elements)

        node = layout.children[0]
        # Should use default 40x40
        assert node.width == 40
        assert node.height == 40

    def test_empty_sheet_connectivity(self):
        """Test with empty sheet connectivity."""
        elements = [
            SourceComponent(source_component_id="R1", name="R1", ftype="simple_resistor")
        ]

        transform = SourceToLayoutTransform()
        layout, _ = transform.transform("root", elements, sheet_connectivity={})

        assert len(layout.edges) == 0

    def test_connectivity_for_different_sheet(self):
        """Test that connectivity for different sheet is ignored."""
        elements = [
            SourceComponent(source_component_id="R1", name="R1", ftype="simple_resistor")
        ]

        sheet_connectivity = {
            "other_sheet": [
                {"trace_id": "t1", "ports": ["R1_1", "R1_2"], "is_inter_group": False}
            ]
        }

        transform = SourceToLayoutTransform()
        layout, _ = transform.transform("root", elements, sheet_connectivity=sheet_connectivity)

        # No edges since connectivity is for different sheet
        assert len(layout.edges) == 0
