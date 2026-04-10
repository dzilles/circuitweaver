"""Tests for the io module (JSON and S-expression I/O)."""

import json
import pytest
from pathlib import Path

from circuitweaver.io import (
    # Circuit (combined)
    read_circuit,
    write_circuit,
    # Source only
    read_source,
    write_source,
    # Schematic only
    read_schematic,
    write_schematic,
    # Layout
    read_layout,
    write_layout,
    # S-expression
    read_s_expr,
    write_s_expr,
    # Element parsing helpers
    parse_element,
    get_element_id_from_raw,
    # Type maps
    ELEMENT_TYPE_MAP,
    SOURCE_TYPE_MAP,
    SCHEMATIC_TYPE_MAP,
)
from circuitweaver.types import (
    SourceComponent,
    SourcePort,
    SourceTrace,
    SourceNet,
    SourceGroup,
    SchematicComponent,
    SchematicTrace,
    SchematicTraceEdge,
    SchematicNetLabel,
    SchematicBox,
    LayoutNode,
    LayoutPort,
    LayoutEdge,
    LayoutLabel,
    Point,
    SExpr,
)


# =============================================================================
# Type Maps Tests
# =============================================================================


class TestTypeMaps:
    """Tests for the type mapping dictionaries."""

    def test_source_type_map_has_all_source_types(self):
        """Test that SOURCE_TYPE_MAP contains all source element types."""
        expected = {
            "source_component",
            "source_port",
            "source_net",
            "source_trace",
            "source_group",
        }
        assert set(SOURCE_TYPE_MAP.keys()) == expected

    def test_schematic_type_map_has_all_schematic_types(self):
        """Test that SCHEMATIC_TYPE_MAP contains all schematic element types."""
        expected = {
            "schematic_component",
            "schematic_port",
            "schematic_trace",
            "schematic_box",
            "schematic_net_label",
            "schematic_hierarchical_pin",
            "schematic_hierarchical_label",
            "schematic_text",
            "schematic_no_connect",
        }
        assert set(SCHEMATIC_TYPE_MAP.keys()) == expected

    def test_element_type_map_combines_both(self):
        """Test that ELEMENT_TYPE_MAP is the union of source and schematic types."""
        expected_keys = set(SOURCE_TYPE_MAP.keys()) | set(SCHEMATIC_TYPE_MAP.keys())
        assert set(ELEMENT_TYPE_MAP.keys()) == expected_keys


# =============================================================================
# parse_element Tests
# =============================================================================


class TestParseElement:
    """Tests for the parse_element function."""

    def test_parse_source_component(self):
        """Test parsing a source_component."""
        raw = {
            "type": "source_component",
            "source_component_id": "comp_1",
            "name": "R1",
            "ftype": "simple_resistor",
        }
        element = parse_element(raw)
        assert isinstance(element, SourceComponent)
        assert element.source_component_id == "comp_1"
        assert element.name == "R1"

    def test_parse_source_port(self):
        """Test parsing a source_port."""
        raw = {
            "type": "source_port",
            "source_port_id": "port_1",
            "source_component_id": "comp_1",
            "name": "1",
        }
        element = parse_element(raw)
        assert isinstance(element, SourcePort)
        assert element.source_port_id == "port_1"

    def test_parse_schematic_component(self):
        """Test parsing a schematic_component."""
        raw = {
            "type": "schematic_component",
            "schematic_component_id": "sch_comp_1",
            "source_component_id": "comp_1",
            "center": {"x": 100, "y": 200},
            "sheet_id": "root",
        }
        element = parse_element(raw)
        assert isinstance(element, SchematicComponent)
        assert element.center.x == 100

    def test_parse_missing_type_raises(self):
        """Test that missing type field raises ValueError."""
        raw = {"source_component_id": "comp_1", "name": "R1"}
        with pytest.raises(ValueError, match="missing 'type' field"):
            parse_element(raw)

    def test_parse_unknown_type_raises(self):
        """Test that unknown type raises ValueError."""
        raw = {"type": "unknown_type", "id": "123"}
        with pytest.raises(ValueError, match="Unknown element type"):
            parse_element(raw)

    def test_parse_invalid_data_raises(self):
        """Test that invalid data raises validation error."""
        raw = {
            "type": "source_component",
            # missing required fields
        }
        with pytest.raises(Exception):  # Pydantic ValidationError
            parse_element(raw)


# =============================================================================
# get_element_id_from_raw Tests
# =============================================================================


class TestGetElementIdFromRaw:
    """Tests for the get_element_id_from_raw function."""

    def test_get_source_component_id(self):
        """Test extracting source_component_id."""
        raw = {"type": "source_component", "source_component_id": "comp_1"}
        assert get_element_id_from_raw(raw) == "comp_1"

    def test_get_source_port_id(self):
        """Test extracting source_port_id."""
        raw = {"type": "source_port", "source_port_id": "port_1"}
        assert get_element_id_from_raw(raw) == "port_1"

    def test_get_schematic_component_id(self):
        """Test extracting schematic_component_id."""
        raw = {"type": "schematic_component", "schematic_component_id": "sch_1"}
        assert get_element_id_from_raw(raw) == "sch_1"

    def test_get_id_returns_none_if_missing(self):
        """Test that None is returned if no ID field found."""
        raw = {"type": "source_component", "name": "R1"}
        assert get_element_id_from_raw(raw) is None

    def test_get_id_from_empty_dict(self):
        """Test extraction from empty dict returns None."""
        assert get_element_id_from_raw({}) is None


# =============================================================================
# Circuit I/O Tests
# =============================================================================


class TestCircuitIO:
    """Tests for read_circuit and write_circuit."""

    @pytest.fixture
    def source_elements(self):
        """Sample source elements."""
        return [
            SourceComponent(
                source_component_id="comp_1",
                name="R1",
                ftype="simple_resistor",
            ),
            SourcePort(
                source_port_id="port_1",
                source_component_id="comp_1",
                name="1",
            ),
        ]

    @pytest.fixture
    def mixed_elements(self, source_elements):
        """Sample mixed source and schematic elements."""
        return source_elements + [
            SchematicComponent(
                schematic_component_id="sch_comp_1",
                source_component_id="comp_1",
                center=Point(x=100, y=200),
                sheet_id="root",
            ),
        ]

    def test_write_and_read_circuit(self, tmp_path, mixed_elements):
        """Test round-trip write then read."""
        file_path = tmp_path / "circuit.json"
        write_circuit(file_path, mixed_elements)

        # File should exist
        assert file_path.exists()

        # Read back
        elements = read_circuit(file_path)
        assert len(elements) == 3
        assert isinstance(elements[0], SourceComponent)
        assert isinstance(elements[1], SourcePort)
        assert isinstance(elements[2], SchematicComponent)

    def test_read_circuit_invalid_json(self, tmp_path):
        """Test reading invalid JSON raises error."""
        file_path = tmp_path / "bad.json"
        file_path.write_text("not valid json {")

        with pytest.raises(json.JSONDecodeError):
            read_circuit(file_path)

    def test_read_circuit_not_a_list(self, tmp_path):
        """Test reading non-list JSON raises ValueError."""
        file_path = tmp_path / "object.json"
        file_path.write_text('{"type": "source_component"}')

        with pytest.raises(ValueError, match="must be a list"):
            read_circuit(file_path)

    def test_read_circuit_file_not_found(self, tmp_path):
        """Test reading non-existent file raises error."""
        with pytest.raises(FileNotFoundError):
            read_circuit(tmp_path / "nonexistent.json")

    def test_write_circuit_custom_indent(self, tmp_path, source_elements):
        """Test writing with custom indentation."""
        file_path = tmp_path / "circuit.json"
        write_circuit(file_path, source_elements, indent=4)

        content = file_path.read_text()
        # With indent=4, we should see 4-space indentation
        assert "    " in content


# =============================================================================
# Source I/O Tests
# =============================================================================


class TestSourceIO:
    """Tests for read_source and write_source."""

    @pytest.fixture
    def source_elements(self):
        """Sample source elements."""
        return [
            SourceComponent(
                source_component_id="comp_1",
                name="R1",
                ftype="simple_resistor",
            ),
            SourcePort(
                source_port_id="port_1",
                source_component_id="comp_1",
                name="1",
            ),
            SourceTrace(
                source_trace_id="trace_1",
                connected_source_port_ids=["port_1"],
            ),
        ]

    def test_write_and_read_source(self, tmp_path, source_elements):
        """Test round-trip write then read."""
        file_path = tmp_path / "source.json"
        write_source(file_path, source_elements)

        elements = read_source(file_path)
        assert len(elements) == 3
        assert all(e.type.startswith("source_") for e in elements)

    def test_write_source_filters_schematic_elements(self, tmp_path):
        """Test that write_source only writes source elements."""
        mixed = [
            SourceComponent(
                source_component_id="comp_1",
                name="R1",
                ftype="simple_resistor",
            ),
            SchematicComponent(
                schematic_component_id="sch_1",
                source_component_id="comp_1",
                center=Point(x=0, y=0),
                sheet_id="root",
            ),
        ]

        file_path = tmp_path / "source.json"
        write_source(file_path, mixed)

        # Read back raw JSON to verify only source element was written
        with open(file_path) as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["type"] == "source_component"

    def test_read_source_rejects_schematic_elements(self, tmp_path):
        """Test that read_source rejects schematic elements."""
        data = [
            {
                "type": "schematic_component",
                "schematic_component_id": "sch_1",
                "source_component_id": "comp_1",
                "center": {"x": 0, "y": 0},
            }
        ]
        file_path = tmp_path / "mixed.json"
        file_path.write_text(json.dumps(data))

        with pytest.raises(ValueError, match="Unknown type"):
            read_source(file_path)


# =============================================================================
# Schematic I/O Tests
# =============================================================================


class TestSchematicIO:
    """Tests for read_schematic and write_schematic."""

    @pytest.fixture
    def schematic_elements(self):
        """Sample schematic elements."""
        return [
            SchematicComponent(
                schematic_component_id="sch_comp_1",
                source_component_id="comp_1",
                center=Point(x=100, y=200),
                sheet_id="root",
            ),
            SchematicTrace(
                schematic_trace_id="sch_trace_1",
                edges=[
                    SchematicTraceEdge(**{"from": Point(x=0, y=0), "to": Point(x=100, y=0)})
                ],
                sheet_id="root",
            ),
            SchematicNetLabel(
                schematic_net_label_id="label_1",
                source_net_id="net_vcc",
                center=Point(x=50, y=50),
                text="VCC",
                anchor_side="left",
                sheet_id="root",
            ),
        ]

    def test_write_and_read_schematic(self, tmp_path, schematic_elements):
        """Test round-trip write then read."""
        file_path = tmp_path / "schematic.json"
        write_schematic(file_path, schematic_elements)

        elements = read_schematic(file_path)
        assert len(elements) == 3
        assert all(e.type.startswith("schematic_") for e in elements)

    def test_write_schematic_filters_source_elements(self, tmp_path):
        """Test that write_schematic only writes schematic elements."""
        mixed = [
            SourceComponent(
                source_component_id="comp_1",
                name="R1",
                ftype="simple_resistor",
            ),
            SchematicComponent(
                schematic_component_id="sch_1",
                source_component_id="comp_1",
                center=Point(x=0, y=0),
                sheet_id="root",
            ),
        ]

        file_path = tmp_path / "schematic.json"
        write_schematic(file_path, mixed)

        with open(file_path) as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["type"] == "schematic_component"

    def test_read_schematic_rejects_source_elements(self, tmp_path):
        """Test that read_schematic rejects source elements."""
        data = [
            {
                "type": "source_component",
                "source_component_id": "comp_1",
                "name": "R1",
                "ftype": "simple_resistor",
            }
        ]
        file_path = tmp_path / "mixed.json"
        file_path.write_text(json.dumps(data))

        with pytest.raises(ValueError, match="Unknown type"):
            read_schematic(file_path)


# =============================================================================
# Layout I/O Tests
# =============================================================================


class TestLayoutIO:
    """Tests for read_layout and write_layout."""

    @pytest.fixture
    def simple_layout(self):
        """A simple layout graph."""
        return LayoutNode(
            id="root",
            width=500,
            height=300,
            children=[
                LayoutNode(
                    id="comp_1",
                    x=50,
                    y=50,
                    width=100,
                    height=60,
                    ports=[
                        LayoutPort(id="port_1", x=0, y=30),
                        LayoutPort(id="port_2", x=100, y=30),
                    ],
                    labels=[
                        LayoutLabel(id="label_1", text="R1", x=10, y=5),
                    ],
                ),
            ],
            edges=[
                LayoutEdge(
                    id="edge_1",
                    sources=["port_1"],
                    targets=["port_2"],
                ),
            ],
        )

    def test_write_and_read_layout(self, tmp_path, simple_layout):
        """Test round-trip write then read."""
        file_path = tmp_path / "layout.json"
        write_layout(file_path, simple_layout)

        # File should exist
        assert file_path.exists()

        # Read back
        layout = read_layout(file_path)
        assert layout.id == "root"
        assert layout.width == 500
        assert len(layout.children) == 1
        assert layout.children[0].id == "comp_1"
        assert len(layout.children[0].ports) == 2
        assert len(layout.edges) == 1

    def test_read_layout_invalid_structure(self, tmp_path):
        """Test reading invalid layout structure."""
        data = {"not": "a layout node"}
        file_path = tmp_path / "bad_layout.json"
        file_path.write_text(json.dumps(data))

        with pytest.raises(Exception):  # Pydantic ValidationError
            read_layout(file_path)

    def test_layout_find_node(self, simple_layout):
        """Test LayoutNode.find_node method."""
        assert simple_layout.find_node("root") == simple_layout
        assert simple_layout.find_node("comp_1") == simple_layout.children[0]
        assert simple_layout.find_node("nonexistent") is None


# =============================================================================
# S-Expression I/O Tests
# =============================================================================


class TestSExprIO:
    """Tests for read_s_expr and write_s_expr."""

    def test_write_and_read_s_expr(self, tmp_path):
        """Test round-trip write then read."""
        sexp = SExpr(
            "kicad_sch",
            SExpr("version", 20231120),
            SExpr("generator", "circuitweaver"),
            SExpr("paper", "A4"),
        )

        file_path = tmp_path / "test.kicad_sch"
        write_s_expr(file_path, sexp)

        # File should exist
        assert file_path.exists()

        # Read back
        result = read_s_expr(file_path)
        assert result.name == "kicad_sch"
        assert result.find("version") is not None
        assert result.get_value("version") == 20231120
        assert result.get_value("generator") == "circuitweaver"

    def test_read_s_expr_nested(self, tmp_path):
        """Test reading deeply nested S-expressions."""
        content = """(symbol "Device:R"
          (property "Reference" "R"
            (at 0 0 0)
            (effects (font (size 1.27 1.27)))
          )
        )"""
        file_path = tmp_path / "symbol.kicad_sym"
        file_path.write_text(content)

        result = read_s_expr(file_path)
        assert result.name == "symbol"
        assert result.args[0] == "Device:R"

        prop = result.find("property")
        assert prop is not None
        assert prop.args[0] == "Reference"

    def test_read_s_expr_with_booleans(self, tmp_path):
        """Test that yes/no are parsed as booleans."""
        content = "(test (in_bom yes) (dnp no))"
        file_path = tmp_path / "bool.sexp"
        file_path.write_text(content)

        result = read_s_expr(file_path)
        assert result.get_value("in_bom") is True
        assert result.get_value("dnp") is False

    def test_read_s_expr_with_numbers(self, tmp_path):
        """Test that numbers are parsed correctly."""
        content = "(at 10 20.5 90)"
        file_path = tmp_path / "numbers.sexp"
        file_path.write_text(content)

        result = read_s_expr(file_path)
        assert result.name == "at"
        assert result.args[0] == 10
        assert result.args[1] == 20.5
        assert result.args[2] == 90

    def test_write_s_expr_quoted_strings(self, tmp_path):
        """Test that strings with spaces are properly quoted."""
        sexp = SExpr("property", "Reference", "U1", SExpr("at", 0, 0))
        file_path = tmp_path / "quoted.sexp"
        write_s_expr(file_path, sexp)

        content = file_path.read_text()
        # Reference and U1 should be in the output
        assert "Reference" in content
        assert "U1" in content


# =============================================================================
# Integration Tests
# =============================================================================


class TestIOIntegration:
    """Integration tests for the io module."""

    def test_circuit_roundtrip_preserves_data(self, tmp_path, simple_led_circuit):
        """Test that a complex circuit survives a write/read cycle."""
        file_path = tmp_path / "circuit.json"
        file_path.write_text(json.dumps(simple_led_circuit, indent=2))

        elements = read_circuit(file_path)

        # Write back
        output_path = tmp_path / "output.json"
        write_circuit(output_path, elements)

        # Read again
        elements2 = read_circuit(output_path)

        # Should have same number of elements
        assert len(elements2) == len(elements)

        # Check specific elements
        components = [e for e in elements2 if isinstance(e, SourceComponent)]
        assert len(components) == 2
        assert {c.name for c in components} == {"R1", "LED1"}

    def test_empty_circuit(self, tmp_path):
        """Test handling of empty element list."""
        file_path = tmp_path / "empty.json"
        write_circuit(file_path, [])

        elements = read_circuit(file_path)
        assert elements == []

    def test_layout_with_nested_children(self, tmp_path):
        """Test layout with deeply nested children."""
        layout = LayoutNode(
            id="root",
            children=[
                LayoutNode(
                    id="group_1",
                    children=[
                        LayoutNode(id="comp_1"),
                        LayoutNode(id="comp_2"),
                    ],
                ),
                LayoutNode(
                    id="group_2",
                    children=[
                        LayoutNode(id="comp_3"),
                    ],
                ),
            ],
        )

        file_path = tmp_path / "nested.json"
        write_layout(file_path, layout)

        result = read_layout(file_path)
        assert result.find_node("comp_1") is not None
        assert result.find_node("comp_3") is not None
        assert result.find_node("nonexistent") is None
