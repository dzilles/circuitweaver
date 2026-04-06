"""Tests for the KiCad schematic writer."""

import pytest

from circuitweaver.compiler.kicad_writer import KiCadWriter, SExp, RawString, GRID_TO_MM
from circuitweaver.types.circuit_json import (
    Point,
    SchematicComponent,
    SchematicTrace,
    SchematicTraceEdge,
    SchematicNetLabel,
    SchematicBox,
    SourceComponent,
)


class TestSExp:
    """Tests for S-Expression builder."""

    def test_empty_sexp(self):
        """Test serializing an empty S-expression."""
        sexp = SExp("empty")
        assert sexp.serialize() == "(empty)"

    def test_simple_sexp_with_args(self):
        """Test serializing S-expression with simple arguments."""
        # Note: digit-only strings get quoted per KiCad S-expression rules
        sexp = SExp("at", 10, 20, 0)
        result = sexp.serialize()
        assert result == "(at 10 20 0)"

    def test_sexp_with_numeric_args(self):
        """Test serializing S-expression with numeric arguments."""
        sexp = SExp("size", 1.27, 1.27)
        result = sexp.serialize()
        assert "(size 1.27 1.27)" in result

    def test_sexp_with_boolean_args(self):
        """Test serializing S-expression with boolean arguments."""
        sexp = SExp("in_bom", True)
        result = sexp.serialize()
        assert "yes" in result

        sexp_false = SExp("dnp", False)
        result_false = sexp_false.serialize()
        assert "no" in result_false

    def test_nested_sexp(self):
        """Test serializing nested S-expressions."""
        inner = SExp("font", SExp("size", 1.27, 1.27))
        outer = SExp("effects", inner)
        result = outer.serialize()
        assert "(effects" in result
        assert "(font" in result
        assert "(size 1.27 1.27)" in result

    def test_sexp_quoting_special_chars(self):
        """Test that special characters trigger quoting."""
        sexp = SExp("property", "Reference", "U1")
        result = sexp.serialize()
        # "Reference" should be quoted because it contains no special chars
        # but let's test one that does
        sexp_special = SExp("text", "hello world")
        result_special = sexp_special.serialize()
        assert '"hello world"' in result_special

    def test_sexp_quoting_empty_string(self):
        """Test that empty strings are quoted."""
        sexp = SExp("value", "")
        result = sexp.serialize()
        assert '""' in result

    def test_sexp_quoting_digit_only(self):
        """Test that digit-only strings are quoted."""
        sexp = SExp("pin", "123")
        result = sexp.serialize()
        assert '"123"' in result

    def test_raw_string_not_quoted(self):
        """Test that RawString values are not quoted."""
        raw = RawString("(symbol Test)")
        sexp = SExp("lib_symbols", raw)
        result = sexp.serialize()
        assert "(symbol Test)" in result
        assert '"(symbol Test)"' not in result


class TestKiCadWriter:
    """Tests for KiCadWriter class."""

    @pytest.fixture
    def writer(self):
        """Create a KiCadWriter instance."""
        return KiCadWriter()

    def test_grid_to_mm_conversion(self, writer):
        """Test grid unit to millimeter conversion."""
        # 1 grid = 0.127mm
        assert writer._grid_to_mm(0) == "0.0000"
        assert writer._grid_to_mm(100) == "12.7000"
        assert writer._grid_to_mm(-100) == "-12.7000"

    def test_new_uuid_format(self, writer):
        """Test that generated UUIDs are valid format."""
        uuid = writer._new_uuid()
        # UUID format: 8-4-4-4-12 hex digits
        parts = uuid.split("-")
        assert len(parts) == 5
        assert len(parts[0]) == 8
        assert len(parts[1]) == 4
        assert len(parts[2]) == 4
        assert len(parts[3]) == 4
        assert len(parts[4]) == 12

    def test_write_trace_single_segment(self, writer):
        """Test writing a trace with a single segment."""
        trace = SchematicTrace(
            schematic_trace_id="trace_1",
            edges=[
                SchematicTraceEdge(**{"from": Point(x=0, y=0), "to": Point(x=100, y=0)})
            ],
        )
        wires = writer._write_trace(trace)
        assert len(wires) == 1
        wire = wires[0]
        assert wire.name == "wire"

    def test_write_trace_multiple_segments(self, writer):
        """Test writing a trace with multiple segments."""
        trace = SchematicTrace(
            schematic_trace_id="trace_1",
            edges=[
                SchematicTraceEdge(**{"from": Point(x=0, y=0), "to": Point(x=100, y=0)}),
                SchematicTraceEdge(**{"from": Point(x=100, y=0), "to": Point(x=100, y=100)}),
            ],
        )
        wires = writer._write_trace(trace)
        assert len(wires) == 2

    def test_write_label(self, writer):
        """Test writing a net label."""
        label = SchematicNetLabel(
            schematic_net_label_id="label_1",
            source_net_id="net_vcc",
            center=Point(x=100, y=200),
            text="VCC",
            anchor_side="left",
        )
        sexp = writer._write_label(label)
        result = sexp.serialize()
        assert "(label" in result
        assert "VCC" in result

    def test_write_box_non_hierarchical(self, writer):
        """Test writing a non-hierarchical box."""
        box = SchematicBox(
            schematic_box_id="box_1",
            x=0,
            y=0,
            width=200,
            height=100,
            is_hierarchical_sheet=False,
        )
        sexp = writer._write_box(box)
        result = sexp.serialize()
        assert "(rectangle" in result
        assert "(start" in result
        assert "(end" in result

    def test_write_project(self, writer):
        """Test writing project file."""
        import json

        result = writer.write_project("my_project", ["root", "power", "mcu"])
        data = json.loads(result)

        assert data["meta"]["filename"] == "my_project.kicad_pro"
        assert data["meta"]["version"] == 3
        assert len(data["sheets"]) == 3

    def test_resolve_lib_id_from_component(self, writer):
        """Test resolving library ID from component."""
        comp = SchematicComponent(
            schematic_component_id="sch_comp_1",
            source_component_id="comp_1",
            center=Point(x=0, y=0),
            symbol_name="Device:R",
        )
        source = None
        lib_id = writer._resolve_lib_id(comp, source)
        assert lib_id == "Device:R"

    def test_resolve_lib_id_from_source(self, writer):
        """Test resolving library ID from source component."""
        comp = SchematicComponent(
            schematic_component_id="sch_comp_1",
            source_component_id="comp_1",
            center=Point(x=0, y=0),
        )
        source = SourceComponent(
            source_component_id="comp_1",
            name="R1",
            symbol_id="Device:R",
        )
        lib_id = writer._resolve_lib_id(comp, source)
        assert lib_id == "Device:R"

    def test_resolve_lib_id_fallback(self, writer):
        """Test fallback library ID when none specified."""
        comp = SchematicComponent(
            schematic_component_id="sch_comp_1",
            source_component_id="comp_1",
            center=Point(x=0, y=0),
        )
        source = SourceComponent(
            source_component_id="comp_1",
            name="U1",
        )
        lib_id = writer._resolve_lib_id(comp, source)
        assert lib_id == "Device:QuestionBlock"

    def test_write_schematic_empty_sheet(self, writer):
        """Test writing an empty schematic sheet."""
        result = writer.write_schematic([], sheet_id="root", source_components={})

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

        assert GRID_TO_MM == Decimal("0.127")
