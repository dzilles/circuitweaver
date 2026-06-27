"""Tests for S-expression serialization and KiCad schematic generation."""

import pytest

from circuitweaver.transform.schematic_to_s_expr import GRID_TO_MM, SchematicToSExprTransform
from circuitweaver.types import (
    Point,
    SchematicBox,
    SchematicComponent,
    SchematicNetLabel,
    SchematicTrace,
    SchematicTraceEdge,
    SourceComponent,
)
from circuitweaver.types.s_expr import RawString, SExpr, serialize


class TestSExpr:
    """Tests for S-Expression builder."""

    def test_empty_sexp(self):
        """Test serializing an empty S-expression."""
        sexp = SExpr("empty")
        assert serialize(sexp) == "(empty)"

    def test_simple_sexp_with_args(self):
        """Test serializing S-expression with simple arguments."""
        # Note: digit-only strings get quoted per KiCad S-expression rules
        sexp = SExpr("at", 10, 20, 0)
        result = serialize(sexp)
        assert result == "(at 10 20 0)"

    def test_sexp_with_numeric_args(self):
        """Test serializing S-expression with numeric arguments."""
        sexp = SExpr("size", 1.27, 1.27)
        result = serialize(sexp)
        assert "(size 1.27 1.27)" in result

    def test_sexp_with_boolean_args(self):
        """Test serializing S-expression with boolean arguments."""
        sexp = SExpr("in_bom", True)
        result = serialize(sexp)
        assert "yes" in result

        sexp_false = SExpr("dnp", False)
        result_false = serialize(sexp_false)
        assert "no" in result_false

    def test_nested_sexp(self):
        """Test serializing nested S-expressions."""
        inner = SExpr("font", SExpr("size", 1.27, 1.27))
        outer = SExpr("effects", inner)
        result = serialize(outer)
        assert "(effects" in result
        assert "(font" in result
        assert "(size 1.27 1.27)" in result

    def test_sexp_quoting_special_chars(self):
        """Test that special characters trigger quoting."""
        sexp = SExpr("property", "Reference", "U1")
        assert serialize(sexp) == "(property Reference U1)"
        # "Reference" should be quoted because it contains no special chars
        # but let's test one that does
        sexp_special = SExpr("text", "hello world")
        result_special = serialize(sexp_special)
        assert '"hello world"' in result_special

    def test_sexp_quoting_empty_string(self):
        """Test that empty strings are quoted."""
        sexp = SExpr("value", "")
        result = serialize(sexp)
        assert '""' in result

    def test_sexp_quoting_digit_only(self):
        """Test that digit-only strings are quoted."""
        sexp = SExpr("pin", "123")
        result = serialize(sexp)
        assert '"123"' in result

    def test_raw_string_not_quoted(self):
        """Test that RawString values are not quoted."""
        raw = RawString("(symbol Test)")
        sexp = SExpr("lib_symbols", raw)
        result = serialize(sexp)
        assert "(symbol Test)" in result
        assert '"(symbol Test)"' not in result


class TestSchematicToSExprTransform:
    """Tests for SchematicToSExprTransform class."""

    @pytest.fixture
    def transform(self):
        """Create a SchematicToSExprTransform instance."""
        return SchematicToSExprTransform()

    def test_grid_to_mm_conversion(self, transform):
        """Test grid unit to millimeter conversion."""
        # 1 grid = 0.127mm
        assert transform._grid_to_mm(0) == "0.0000"
        assert transform._grid_to_mm(100) == "12.7000"
        assert transform._grid_to_mm(-100) == "-12.7000"

    def test_new_uuid_format(self, transform):
        """Test that generated UUIDs are valid format."""
        uuid = transform._new_uuid()
        # UUID format: 8-4-4-4-12 hex digits
        parts = uuid.split("-")
        assert len(parts) == 5
        assert len(parts[0]) == 8
        assert len(parts[1]) == 4
        assert len(parts[2]) == 4
        assert len(parts[3]) == 4
        assert len(parts[4]) == 12

    def test_transform_trace_single_segment(self, transform):
        """Test transforming a trace with a single segment."""
        trace = SchematicTrace(
            schematic_trace_id="trace_1",
            edges=[
                SchematicTraceEdge(**{"from": Point(x=0, y=0), "to": Point(x=100, y=0)})
            ],
            sheet_id="root",
        )
        wires = transform._transform_trace(trace)
        assert len(wires) == 1
        wire = wires[0]
        assert wire.name == "wire"

    def test_transform_trace_multiple_segments(self, transform):
        """Test transforming a trace with multiple segments."""
        trace = SchematicTrace(
            schematic_trace_id="trace_1",
            edges=[
                SchematicTraceEdge(**{"from": Point(x=0, y=0), "to": Point(x=100, y=0)}),
                SchematicTraceEdge(**{"from": Point(x=100, y=0), "to": Point(x=100, y=100)}),
            ],
            sheet_id="root",
        )
        wires = transform._transform_trace(trace)
        assert len(wires) == 2

    def test_transform_label(self, transform):
        """Test transforming a net label."""
        label = SchematicNetLabel(
            schematic_net_label_id="label_1",
            source_net_id="net_vcc",
            center=Point(x=100, y=200),
            text="VCC",
            anchor_side="left",
            sheet_id="root",
        )
        sexp = transform._transform_label(label)
        result = serialize(sexp)
        assert "(label" in result
        assert "VCC" in result

    def test_transform_global_label(self, transform):
        """Test transforming a global net label."""
        label = SchematicNetLabel(
            schematic_net_label_id="label_gnd",
            source_net_id="GND",
            center=Point(x=100, y=200),
            text="GND",
            anchor_side="left",
            sheet_id="root",
            is_global=True,
        )
        sexp = transform._transform_label(label)
        result = serialize(sexp)
        assert "(global_label" in result
        assert "GND" in result

    def test_transform_box_non_hierarchical(self, transform):
        """Test transforming a non-hierarchical box."""
        box = SchematicBox(
            schematic_box_id="box_1",
            x=0,
            y=0,
            width=200,
            height=100,
            is_hierarchical_sheet=False,
            sheet_id="root",
        )
        sexp = transform._transform_box(box)
        result = serialize(sexp)
        assert "(rectangle" in result
        assert "(start" in result
        assert "(end" in result

    def test_transform_project(self, transform):
        """Test transforming project file."""
        import json

        result = transform.transform_project("my_project", ["root", "power", "mcu"])
        data = json.loads(result)

        assert data["meta"]["filename"] == "my_project.kicad_pro"
        assert data["meta"]["version"] == 3
        assert len(data["sheets"]) == 3

    def test_resolve_lib_id_from_component(self, transform):
        """Test resolving library ID from component."""
        comp = SchematicComponent(
            schematic_component_id="sch_comp_1",
            source_component_id="comp_1",
            center=Point(x=0, y=0),
            symbol_name="Device:R",
            sheet_id="root",
        )
        source = None
        lib_id = transform._resolve_lib_id(comp, source)
        assert lib_id == "Device:R"

    def test_resolve_lib_id_from_source(self, transform):
        """Test resolving library ID from source component."""
        comp = SchematicComponent(
            schematic_component_id="sch_comp_1",
            source_component_id="comp_1",
            center=Point(x=0, y=0),
            sheet_id="root",
        )
        source = SourceComponent(
            source_component_id="comp_1",
            name="R1",
            symbol_id="Device:R",
        )
        lib_id = transform._resolve_lib_id(comp, source)
        assert lib_id == "Device:R"

    def test_resolve_lib_id_fallback(self, transform):
        """Test fallback library ID when none specified."""
        comp = SchematicComponent(
            schematic_component_id="sch_comp_1",
            source_component_id="comp_1",
            center=Point(x=0, y=0),
            sheet_id="root",
        )
        source = SourceComponent(
            source_component_id="comp_1",
            name="U1",
        )
        lib_id = transform._resolve_lib_id(comp, source)
        assert lib_id == "Device:QuestionBlock"

    def test_transform_empty_sheet(self, transform):
        """Test transforming an empty schematic sheet."""
        sexp = transform.transform([], sheet_id="root", source_components={})
        result = serialize(sexp)

        assert "(kicad_sch" in result
        assert "(version" in result
        assert "(generator" in result
        assert "(paper" in result
        assert "(lib_symbols" in result


class TestGridToMmConstant:
    """Tests for the grid to mm conversion constant."""

    def test_grid_constant_value(self):
        """Test that GRID_TO_MM has the correct value."""
        from decimal import Decimal

        assert Decimal("0.127") == GRID_TO_MM
