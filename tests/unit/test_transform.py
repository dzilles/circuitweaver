"""Tests for the transform module (Source → Layout → Schematic → S-expr)."""

import pytest

from circuitweaver.transform import (
    FTYPE_SYMBOL_MAP,
    LayoutRegistry,
    # Layout → Schematic
    LayoutToSchematicTransform,
    # Schematic → S-expr
    SchematicToSExprTransform,
    # Source → Layout
    SourceToLayoutTransform,
    get_effective_symbol_id,
    snap_to_grid,
)
from circuitweaver.types import (
    LayoutEdge,
    LayoutEdgeSection,
    LayoutNode,
    LayoutPoint,
    Point,
    SchematicBox,
    SchematicComponent,
    SchematicHierarchicalLabel,
    SchematicHierarchicalPin,
    SchematicNetLabel,
    SchematicNoConnect,
    SchematicText,
    SchematicTrace,
    SchematicTraceEdge,
    SheetConnection,
    SourceComponent,
    SourceGroup,
    SourcePort,
)
from circuitweaver.types import (
    s_expr_serialize as serialize,
)

# =============================================================================
# FTYPE_SYMBOL_MAP Tests
# =============================================================================


class TestFtypeSymbolMap:
    """Tests for the FTYPE_SYMBOL_MAP constant."""

    def test_ftype_map_has_common_types(self):
        """Test that common ftypes are mapped."""
        assert "simple_resistor" in FTYPE_SYMBOL_MAP
        assert "simple_capacitor" in FTYPE_SYMBOL_MAP
        assert "simple_led" in FTYPE_SYMBOL_MAP

    def test_ftype_map_values_are_valid_symbol_ids(self):
        """Test that mapped values look like valid KiCad symbol IDs."""
        for ftype, symbol_id in FTYPE_SYMBOL_MAP.items():
            assert ":" in symbol_id, f"Symbol ID for {ftype} should contain ':'"


# =============================================================================
# get_effective_symbol_id Tests
# =============================================================================


class TestGetEffectiveSymbolId:
    """Tests for the get_effective_symbol_id function."""

    def test_returns_explicit_symbol_id(self):
        """Test that explicit symbol_id takes precedence."""
        comp = SourceComponent(
            source_component_id="R1",
            name="R1",
            symbol_id="Device:R_US",
            ftype="simple_resistor",
        )
        assert get_effective_symbol_id(comp) == "Device:R_US"

    def test_falls_back_to_ftype(self):
        """Test fallback to ftype mapping when no symbol_id."""
        comp = SourceComponent(
            source_component_id="R1",
            name="R1",
            ftype="simple_resistor",
        )
        assert get_effective_symbol_id(comp) == "Device:R"

    def test_returns_none_when_unknown_ftype(self):
        """Test returns None when ftype is not mapped."""
        comp = SourceComponent(
            source_component_id="U1",
            name="U1",
            ftype="custom_ic",
        )
        assert get_effective_symbol_id(comp) is None

    def test_returns_none_when_no_symbol_or_ftype(self):
        """Test returns None when neither symbol_id nor ftype is useful."""
        comp = SourceComponent(
            source_component_id="X1",
            name="X1",
        )
        assert get_effective_symbol_id(comp) is None


# =============================================================================
# LayoutRegistry Tests
# =============================================================================


class TestLayoutRegistry:
    """Tests for the LayoutRegistry class."""

    def test_register_and_lookup_node(self):
        """Test registering and looking up a node."""
        registry = LayoutRegistry()
        comp = SourceComponent(source_component_id="R1", name="R1")

        registry.register_node(comp, "layout_R1")

        assert registry.element_to_node["R1"] == "layout_R1"
        assert registry.get_element_by_layout_id("layout_R1") == comp

    def test_register_and_lookup_port(self):
        """Test registering and looking up a port."""
        registry = LayoutRegistry()
        port = SourcePort(source_port_id="port_1", source_component_id="R1", name="1")

        registry.register_port(port, "R1:1")

        assert registry.element_to_port["port_1"] == "R1:1"
        assert registry.get_element_by_layout_id("R1:1") == port

    def test_lookup_with_parent_prefix(self):
        """Test looking up element with 'parent:port' format."""
        registry = LayoutRegistry()
        port = SourcePort(source_port_id="port_1", source_component_id="R1", name="1")

        registry.register_port(port, "port_1")

        # Should find it even with parent prefix
        result = registry.get_element_by_layout_id("R1:port_1")
        assert result == port

    def test_lookup_nonexistent_returns_none(self):
        """Test looking up nonexistent ID returns None."""
        registry = LayoutRegistry()
        assert registry.get_element_by_layout_id("nonexistent") is None


# =============================================================================
# SourceToLayoutTransform Tests
# =============================================================================


class TestSourceToLayoutTransform:
    """Tests for the SourceToLayoutTransform class."""

    def test_empty_elements(self):
        """Test transforming empty element list."""
        transform = SourceToLayoutTransform()
        layout, registry = transform.transform("root", [])

        assert layout.id == "root"
        assert len(layout.children) == 0
        assert len(layout.edges) == 0

    def test_single_component(self):
        """Test transforming a single component."""
        transform = SourceToLayoutTransform()
        elements = [
            SourceComponent(source_component_id="R1", name="R1", ftype="simple_resistor")
        ]

        layout, registry = transform.transform("root", elements)

        assert len(layout.children) == 1
        assert layout.children[0].id == "R1"
        assert "R1" in registry.element_to_node

    def test_multiple_components(self):
        """Test transforming multiple components."""
        transform = SourceToLayoutTransform()
        elements = [
            SourceComponent(source_component_id="R1", name="R1"),
            SourceComponent(source_component_id="C1", name="C1"),
            SourceComponent(source_component_id="LED1", name="LED1"),
        ]

        layout, registry = transform.transform("root", elements)

        assert len(layout.children) == 3
        child_ids = {c.id for c in layout.children}
        assert child_ids == {"R1", "C1", "LED1"}

    def test_root_has_layout_options(self):
        """Test that root node has ELK layout options."""
        transform = SourceToLayoutTransform()
        layout, _ = transform.transform("test_sheet", [])

        assert "org.eclipse.elk.algorithm" in layout.layoutOptions
        assert layout.layoutOptions["org.eclipse.elk.algorithm"] == "layered"

    def test_component_node_has_port_constraints(self):
        """Test that component nodes have fixed port constraints."""
        transform = SourceToLayoutTransform()
        elements = [
            SourceComponent(source_component_id="R1", name="R1")
        ]

        layout, _ = transform.transform("root", elements)

        comp_node = layout.children[0]
        assert "org.eclipse.elk.portConstraints" in comp_node.layoutOptions


# =============================================================================
# snap_to_grid Tests
# =============================================================================


class TestSnapToGrid:
    """Tests for the snap_to_grid function."""

    def test_snap_exact_grid_point(self):
        """Test snapping value already on grid."""
        assert snap_to_grid(100.0) == 100.0
        assert snap_to_grid(50.0) == 50.0

    def test_snap_to_nearest_lower(self):
        """Test snapping to nearest lower grid point."""
        assert snap_to_grid(14.0) == 10.0
        assert snap_to_grid(103.0) == 100.0

    def test_snap_to_nearest_higher(self):
        """Test snapping to nearest higher grid point."""
        assert snap_to_grid(16.0) == 20.0
        assert snap_to_grid(107.0) == 110.0

    def test_snap_halfway_rounds_up(self):
        """Test that halfway values round to even (Python's default)."""
        # 15.0 is exactly between 10 and 20, should round to 20 (nearest even is 2)
        assert snap_to_grid(15.0) == 20.0

    def test_snap_negative_values(self):
        """Test snapping negative values."""
        assert snap_to_grid(-14.0) == -10.0
        assert snap_to_grid(-16.0) == -20.0

    def test_snap_custom_grid_size(self):
        """Test snapping with custom grid size."""
        assert snap_to_grid(27.0, grid_size=5.0) == 25.0
        assert snap_to_grid(23.0, grid_size=5.0) == 25.0

    def test_snap_zero(self):
        """Test snapping zero."""
        assert snap_to_grid(0.0) == 0.0


# =============================================================================
# LayoutToSchematicTransform Tests
# =============================================================================


class TestLayoutToSchematicTransform:
    """Tests for the LayoutToSchematicTransform class."""

    def test_empty_layout(self):
        """Test transforming empty layout."""
        transform = LayoutToSchematicTransform()
        layout = LayoutNode(id="root")
        registry = LayoutRegistry()

        result = transform.transform("root", layout, registry, [])

        assert result == []

    def test_component_creates_schematic_component(self):
        """Test that component nodes create SchematicComponents."""
        transform = LayoutToSchematicTransform()

        comp = SourceComponent(source_component_id="R1", name="R1")
        registry = LayoutRegistry()
        registry.register_node(comp, "R1")

        layout = LayoutNode(
            id="root",
            children=[
                LayoutNode(id="R1", x=100, y=200, width=40, height=40)
            ],
        )

        result = transform.transform("root", layout, registry, [comp])

        sch_comps = [e for e in result if isinstance(e, SchematicComponent)]
        assert len(sch_comps) == 1
        assert sch_comps[0].source_component_id == "R1"
        assert sch_comps[0].sheet_id == "root"

    def test_component_position_is_snapped(self):
        """Test that component positions are snapped to grid."""
        transform = LayoutToSchematicTransform(grid_size=10.0)

        comp = SourceComponent(source_component_id="R1", name="R1")
        registry = LayoutRegistry()
        registry.register_node(comp, "R1")

        layout = LayoutNode(
            id="root",
            children=[
                LayoutNode(id="R1", x=103, y=197, width=40, height=40)
            ],
        )

        result = transform.transform("root", layout, registry, [comp])

        sch_comp = [e for e in result if isinstance(e, SchematicComponent)][0]
        # Position should be snapped
        assert sch_comp.center.x == 100.0
        assert sch_comp.center.y == 200.0

    def test_edges_create_traces(self):
        """Test that layout edges create SchematicTraces."""
        transform = LayoutToSchematicTransform()

        registry = LayoutRegistry()

        layout = LayoutNode(
            id="root",
            edges=[
                LayoutEdge(
                    id="e_trace_1",
                    sources=["R1:1"],
                    targets=["C1:1"],
                    sections=[
                        LayoutEdgeSection(
                            id="sec_1",
                            startPoint=LayoutPoint(x=0, y=0),
                            endPoint=LayoutPoint(x=100, y=0),
                        )
                    ],
                )
            ],
        )

        result = transform.transform("root", layout, registry, [])

        traces = [e for e in result if isinstance(e, SchematicTrace)]
        assert len(traces) == 1
        assert traces[0].sheet_id == "root"
        assert len(traces[0].edges) >= 1

    def test_edge_position_is_snapped_correctly(self):
        """Test that edge snapping uses absolute raw coordinates, not pre-snapped parent coordinates.
        This prevents accumulating rounding errors (e.g. snap(5 + snap(105)) vs snap(5 + 105)).
        """
        transform = LayoutToSchematicTransform(grid_size=10.0)
        registry = LayoutRegistry()

        # Parent node is at 105 (snaps to 110)
        # Edge starts at relative 5.
        # If snapped incorrectly: snap(5 + snap(105)) = snap(5 + 110) = 120 (Python rounds 115 to nearest even 120)
        # If snapped correctly: snap(5 + 105) = snap(110) = 110
        layout = LayoutNode(
            id="root",
            x=105,
            y=105,
            edges=[
                LayoutEdge(
                    id="e_trace_1",
                    sources=["R1:1"],
                    targets=["C1:1"],
                    sections=[
                        LayoutEdgeSection(
                            id="sec_1",
                            startPoint=LayoutPoint(x=5, y=5),
                            endPoint=LayoutPoint(x=15, y=15),
                        )
                    ],
                )
            ],
        )

        result = transform.transform("root", layout, registry, [])

        traces = [e for e in result if isinstance(e, SchematicTrace)]
        assert len(traces) == 1

        # The correct snapped absolute position is snap(105 + 5) = snap(110) = 110
        assert traces[0].edges[0].from_.x == 110.0
        assert traces[0].edges[0].from_.y == 110.0

        # The correct snapped absolute end position is snap(105 + 15) = snap(120) = 120.
        # Diagonal ELK sections may be split into orthogonal schematic segments.
        assert traces[0].edges[-1].to.x == 120.0
        assert traces[0].edges[-1].to.y == 120.0

    def test_edge_with_bendpoints(self):
        """Test edge with bendpoints creates multi-segment trace."""
        transform = LayoutToSchematicTransform()

        registry = LayoutRegistry()

        layout = LayoutNode(
            id="root",
            edges=[
                LayoutEdge(
                    id="e_trace_1",
                    sources=["R1:1"],
                    targets=["C1:1"],
                    sections=[
                        LayoutEdgeSection(
                            id="sec_1",
                            startPoint=LayoutPoint(x=0, y=0),
                            endPoint=LayoutPoint(x=100, y=100),
                            bendPoints=[LayoutPoint(x=100, y=0)],
                        )
                    ],
                )
            ],
        )

        result = transform.transform("root", layout, registry, [])

        traces = [e for e in result if isinstance(e, SchematicTrace)]
        assert len(traces) == 1
        # Should have 2 edges: (0,0)→(100,0) and (100,0)→(100,100)
        assert len(traces[0].edges) == 2


# =============================================================================
# SchematicToSExprTransform Tests (beyond test_kicad_writer.py)
# =============================================================================


class TestSchematicToSExprTransform:
    """Additional tests for SchematicToSExprTransform."""

    @pytest.fixture
    def transform(self):
        """Create a SchematicToSExprTransform instance."""
        return SchematicToSExprTransform()

    def test_transform_text(self, transform):
        """Test transforming schematic text."""
        text = SchematicText(
            schematic_text_id="text_1",
            position=Point(x=100, y=200),
            text="Test annotation",
            rotation=0,
            sheet_id="root",
        )
        sexp = transform._transform_text(text)
        result = serialize(sexp)
        assert "(text" in result
        assert "Test annotation" in result

    def test_transform_hierarchical_label(self, transform):
        """Test transforming hierarchical label."""
        label = SchematicHierarchicalLabel(
            schematic_hierarchical_label_id="hlabel_1",
            source_net_id="net_clk",
            center=Point(x=50, y=100),
            text="CLK",
            anchor_side="right",
            sheet_id="sub_sheet",
        )
        sexp = transform._transform_hierarchical_label(label)
        result = serialize(sexp)
        assert "(hierarchical_label" in result
        assert "CLK" in result
        assert "(shape" in result

    def test_transform_no_connect_with_position(self, transform):
        """Test transforming no-connect with position."""
        nc = SchematicNoConnect(
            schematic_no_connect_id="nc_1",
            position=Point(x=75, y=150),
            sheet_id="root",
        )
        sexp = transform._transform_no_connect(nc)
        assert sexp is not None
        result = serialize(sexp)
        assert "(no_connect" in result
        assert "(at" in result

    def test_transform_no_connect_without_position(self, transform):
        """Test that no-connect without position returns None."""
        nc = SchematicNoConnect(
            schematic_no_connect_id="nc_1",
            sheet_id="root",
        )
        sexp = transform._transform_no_connect(nc)
        assert sexp is None

    def test_transform_hierarchical_sheet(self, transform):
        """Test transforming hierarchical sheet box with pins."""
        box = SchematicBox(
            schematic_box_id="box_mcu",
            x=100,
            y=100,
            width=200,
            height=150,
            is_hierarchical_sheet=True,
            name="MCU_SubSheet",
            sheet_id="root",
        )
        pins = [
            SchematicHierarchicalPin(
                schematic_hierarchical_pin_id="hpin_1",
                source_net_id="net_vcc",
                schematic_box_id="box_mcu",
                center=Point(x=100, y=120),
                text="VCC",
                sheet_id="root",
            ),
            SchematicHierarchicalPin(
                schematic_hierarchical_pin_id="hpin_2",
                source_net_id="net_gnd",
                schematic_box_id="box_mcu",
                center=Point(x=300, y=120),
                text="GND",
                sheet_id="root",
            ),
        ]
        sexp = transform._transform_hierarchical_sheet(box, pins)
        result = serialize(sexp)
        assert "(sheet" in result
        assert "(size" in result
        assert "Sheetname" in result
        assert "Sheetfile" in result
        assert "(pin" in result
        assert "VCC" in result
        assert "GND" in result

    def test_transform_full_sheet(self, transform):
        """Test transforming a full sheet with multiple elements."""
        elements = [
            SchematicComponent(
                schematic_component_id="sch_R1",
                source_component_id="R1",
                center=Point(x=100, y=100),
                sheet_id="root",
            ),
            SchematicTrace(
                schematic_trace_id="trace_1",
                edges=[
                    SchematicTraceEdge(**{"from": Point(x=0, y=0), "to": Point(x=100, y=0)})
                ],
                sheet_id="root",
            ),
            SchematicNetLabel(
                schematic_net_label_id="label_1",
                source_net_id="net_vcc",
                center=Point(x=50, y=0),
                text="VCC",
                anchor_side="left",
                sheet_id="root",
            ),
        ]
        source_components = {
            "R1": SourceComponent(source_component_id="R1", name="R1", ftype="simple_resistor")
        }

        sexp = transform.transform(elements, "root", source_components)
        result = serialize(sexp)

        assert "(kicad_sch" in result
        assert "(version" in result
        assert "(lib_symbols" in result
        assert "(wire" in result
        assert "(label" in result
        assert "VCC" in result

    def test_transform_project(self, transform):
        """Test project file transformation."""
        import json

        result = transform.transform_project("my_circuit", ["root", "power", "mcu"])
        data = json.loads(result)

        assert data["meta"]["filename"] == "my_circuit.kicad_pro"
        assert data["meta"]["version"] == 3
        assert len(data["sheets"]) == 3
        assert data["sheets"][0] == ["Root", "my_circuit.kicad_sch"]

    def test_grid_to_mm_conversion(self, transform):
        """Test grid to millimeter conversion."""
        # 1 grid = 0.127mm
        assert transform._grid_to_mm(0) == "0.0000"
        assert transform._grid_to_mm(100) == "12.7000"
        assert transform._grid_to_mm(-100) == "-12.7000"
        # Fractional
        assert transform._grid_to_mm(10) == "1.2700"

    def test_uuid_format(self, transform):
        """Test that generated UUIDs have correct format."""
        uuid = transform._new_uuid()
        parts = uuid.split("-")
        assert len(parts) == 5
        assert len(parts[0]) == 8
        assert len(parts[1]) == 4
        assert len(parts[2]) == 4
        assert len(parts[3]) == 4
        assert len(parts[4]) == 12


# =============================================================================
# Integration Tests
# =============================================================================


class TestTransformPipeline:
    """Integration tests for the full transform pipeline."""

    def test_source_to_layout_to_schematic(self):
        """Test transforming source → layout → schematic."""
        # 1. Source elements
        source_elements = [
            SourceComponent(source_component_id="R1", name="R1", ftype="simple_resistor"),
            SourceComponent(source_component_id="C1", name="C1", ftype="simple_capacitor"),
        ]

        # 2. Source → Layout
        source_to_layout = SourceToLayoutTransform()
        layout, registry = source_to_layout.transform("root", source_elements)

        assert len(layout.children) == 2

        # Simulate ELK positioning
        for i, child in enumerate(layout.children):
            child.x = 100 + i * 150
            child.y = 100

        # 3. Layout → Schematic
        layout_to_schematic = LayoutToSchematicTransform()
        schematic_elements = layout_to_schematic.transform(
            "root", layout, registry, source_elements
        )

        # Should have schematic components
        sch_comps = [e for e in schematic_elements if isinstance(e, SchematicComponent)]
        assert len(sch_comps) == 2

    def test_schematic_to_sexpr_roundtrip(self):
        """Test that schematic elements survive S-expr transformation."""
        schematic_elements = [
            SchematicComponent(
                schematic_component_id="sch_R1",
                source_component_id="R1",
                center=Point(x=100, y=100),
                sheet_id="root",
            ),
            SchematicTrace(
                schematic_trace_id="trace_1",
                edges=[
                    SchematicTraceEdge(**{"from": Point(x=50, y=100), "to": Point(x=100, y=100)})
                ],
                sheet_id="root",
            ),
        ]
        source_components = {
            "R1": SourceComponent(source_component_id="R1", name="R1")
        }

        transform = SchematicToSExprTransform()
        sexp = transform.transform(schematic_elements, "root", source_components)

        # Should be valid SExpr
        assert sexp.name == "kicad_sch"
        assert sexp.find("version") is not None
        assert sexp.find("lib_symbols") is not None

        # Serialize should work
        result = serialize(sexp)
        assert "(kicad_sch" in result
        assert "(wire" in result


# =============================================================================
# Hierarchy and Smart Connectivity Tests
# =============================================================================


class TestTransformHierarchy:
    """Tests for hierarchical nesting and connectivity rules."""

    def test_subgroup_nesting(self):
        """Test that SourceGroup (is_subcircuit=False) creates a nested LayoutNode."""
        transform = SourceToLayoutTransform()
        elements = [
            SourceGroup(
                source_group_id="group_1",
                name="Subgroup 1",
                is_subcircuit=False,
            ),
            SourceComponent(
                source_component_id="R1",
                name="R1",
                source_group_id="group_1",
            ),
        ]

        layout, registry = transform.transform("root", elements)

        # Root should have 1 child (the subgroup box)
        assert len(layout.children) == 1
        subgroup_node = layout.children[0]
        assert subgroup_node.id == "box_group_1"

        # Subgroup box should have 1 child (the component)
        assert len(subgroup_node.children) == 1
        assert subgroup_node.children[0].id == "R1"

    def test_intra_group_wires(self):
        """Test that connections within the same subgroup use wires (LayoutEdge)."""
        transform = SourceToLayoutTransform()
        elements = [
            SourceGroup(source_group_id="g1", is_subcircuit=False),
            SourceComponent(source_component_id="R1", name="R1", source_group_id="g1"),
            SourceComponent(source_component_id="R2", name="R2", source_group_id="g1"),
            SourcePort(source_port_id="p_r1_1", source_component_id="R1", name="1", pin_number=1),
            SourcePort(source_port_id="p_r2_1", source_component_id="R2", name="1", pin_number=1),
        ]

        connectivity = {
            "root": [
                SheetConnection(
                    net_id="t1",
                    trace_ids=("t1",),
                    sheet_id="root",
                    endpoint_port_ids=("p_r1_1", "p_r2_1"),
                    render_kind="wire",
                    label_text="NET_t1",
                    hierarchical_label_text="HPIN_t1",
                )
            ]
        }

        layout, registry = transform.transform("root", elements, sheet_connectivity=connectivity)

        # Should have a wire (edge) in the root node (or subgroup node)
        assert len(layout.edges) == 1
        assert layout.edges[0].id == "e_t1_p_r2_1"

    def test_inter_group_labels(self):
        """Test that connections between different subgroups use labels instead of wires."""
        transform = SourceToLayoutTransform()
        elements = [
            SourceGroup(source_group_id="g1", is_subcircuit=False),
            SourceGroup(source_group_id="g2", is_subcircuit=False),
            SourceComponent(source_component_id="R1", name="R1", source_group_id="g1"),
            SourceComponent(source_component_id="R2", name="R2", source_group_id="g2"),
            SourcePort(source_port_id="p_r1_1", source_component_id="R1", name="1", pin_number=1),
            SourcePort(source_port_id="p_r2_1", source_component_id="R2", name="1", pin_number=1),
        ]

        connectivity = {
            "root": [
                SheetConnection(
                    net_id="t1",
                    trace_ids=("t1",),
                    sheet_id="root",
                    endpoint_port_ids=("p_r1_1", "p_r2_1"),
                    render_kind="local_label",
                    label_text="NET_t1",
                    hierarchical_label_text="HPIN_t1",
                    is_inter_group=True,
                )
            ]
        }

        layout, registry = transform.transform("root", elements, sheet_connectivity=connectivity)

        # Should NOT have a wire between components
        wire_edges = [e for e in layout.edges if not e.id.startswith("e_label_")]
        assert len(wire_edges) == 0

        # Should have label nodes and edges connecting ports to labels
        # Two labels, one for each port
        # In our implementation, label nodes are inside the parent box
        g1_node = layout.find_node("box_g1")
        g2_node = layout.find_node("box_g2")

        # Check for label nodes inside boxes
        assert any(c.id.startswith("label_node_") for c in g1_node.children)
        assert any(c.id.startswith("label_node_") for c in g2_node.children)

        # Check for label edges inside boxes
        assert any(e.id.startswith("e_label_") for e in g1_node.edges)
        assert any(e.id.startswith("e_label_") for e in g2_node.edges)

        # Add mock routed sections to edges since we aren't running the real ELK router here
        for e in g1_node.edges:
            if e.id.startswith("e_label_"):
                e.sections.append(LayoutEdgeSection(
                    id=e.id + "_sec",
                    startPoint=LayoutPoint(x=10, y=10),
                    endPoint=LayoutPoint(x=20, y=10)
                ))
        for e in g2_node.edges:
            if e.id.startswith("e_label_"):
                e.sections.append(LayoutEdgeSection(
                    id=e.id + "_sec",
                    startPoint=LayoutPoint(x=30, y=10),
                    endPoint=LayoutPoint(x=40, y=10)
                ))

        # 2. Layout → Schematic
        sch_transform = LayoutToSchematicTransform()
        schematic_elements = sch_transform.transform("root", layout, registry, elements)

        # Verify SchematicNetLabel elements are in the final schematic output
        labels = [e for e in schematic_elements if isinstance(e, SchematicNetLabel)]
        assert len(labels) == 2

        # Verify labels have been assigned non-zero coordinates
        for label in labels:
            assert label.center.x != 0.0 or label.center.y != 0.0

    def test_nested_subgroups(self):
        """Test multiple levels of nesting."""
        transform = SourceToLayoutTransform()
        elements = [
            SourceGroup(source_group_id="outer", is_subcircuit=False),
            SourceGroup(
                source_group_id="inner", is_subcircuit=False, parent_source_group_id="outer"
            ),
            SourceComponent(source_component_id="R1", name="R1", source_group_id="inner"),
        ]

        layout, registry = transform.transform("root", elements)

        outer_box = layout.find_node("box_outer")
        assert outer_box is not None
        inner_box = outer_box.find_node("box_inner")
        assert inner_box is not None
        assert inner_box.find_node("R1") is not None

    def test_subgroup_is_not_hierarchical_sheet(self):
        """Test that a subgroup (is_subcircuit=False) results in a non-hierarchical SchematicBox."""
        # 1. Source → Layout
        transform = SourceToLayoutTransform()
        group = SourceGroup(source_group_id="g1", is_subcircuit=False)
        layout, registry = transform.transform("root", [group])

        # 2. Layout → Schematic
        sch_transform = LayoutToSchematicTransform()
        schematic_elements = sch_transform.transform("root", layout, registry, [group])

        boxes = [e for e in schematic_elements if isinstance(e, SchematicBox)]
        assert len(boxes) == 1
        assert boxes[0].is_hierarchical_sheet is False
