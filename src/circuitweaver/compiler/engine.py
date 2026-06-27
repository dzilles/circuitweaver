"""Main compilation engine for CircuitWeaver.

Orchestrates the full pipeline from Source elements to KiCad files:
1. Source → Layout (ELK graph)
2. Layout → Layout (auto-routing via ELK)
3. Layout → Schematic (positioned elements)
4. Schematic → S-expression (KiCad format)
5. S-expression → .kicad_sch files
"""

import json
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from circuitweaver.compiler.auto_router import AutoRouter
from circuitweaver.compiler.connectivity import build_connection_plan, build_sheet_connectivity
from circuitweaver.compiler.global_nets import GlobalNetResolver
from circuitweaver.compiler.layout_quality import LayoutQualityChecker, LayoutQualityReport
from circuitweaver.library.pinout import get_symbol_info
from circuitweaver.project import CircuitProject, KiCadProject
from circuitweaver.results import Diagnostic, OutputArtifact, StageResult
from circuitweaver.transform import (
    LayoutToSchematicTransform,
    SchematicToSExprTransform,
    SourceToLayoutTransform,
    get_effective_symbol_id,
)
from circuitweaver.types import (
    CircuitElement,
    LayoutNode,
    SchematicComponent,
    SchematicPort,
    SourceComponent,
    SourceGroup,
    SourceNet,
    SourcePort,
    SourceTrace,
    get_element_id,
    s_expr_serialize,
)

logger = logging.getLogger(__name__)

DEBUG_ELK = os.environ.get("CIRCUITWEAVER_DEBUG_ELK", "").lower() in ("1", "true", "yes")


def _format_stage_errors(result: StageResult[Any]) -> str:
    if not result.errors:
        return f"Stage '{result.stage}' failed without a structured error."
    return "; ".join(f"{d.code}: {d.message}" for d in result.errors)


class CompileEngine:
    """Main engine for compiling Circuit JSON to KiCad schematics.

    Orchestrates the full transformation pipeline and file output.
    """

    def __init__(
        self,
        helper_path: str | None = None,
        kicad_cli_path: str = "kicad-cli",
        router: AutoRouter | None = None,
        symbol_lookup: Callable[[str], Any] | None = None,
        erc_runner: Callable[[Path], dict[str, Any]] | None = None,
        uuid_factory: Callable[[], str] | None = None,
    ):
        """Initialize the compile engine.

        Args:
            helper_path: Path to the ELK layout helper JS file.
            kicad_cli_path: Path to kicad-cli for ERC checks.
        """
        self.router = router or AutoRouter(helper_path=Path(helper_path) if helper_path else None)
        self.kicad_cli_path = kicad_cli_path
        self.symbol_lookup = symbol_lookup or get_symbol_info
        self.erc_runner = erc_runner
        self.uuid_factory = uuid_factory
        self.last_layout_artifacts: dict[str, list[dict[str, Any]]] = {
            "elk_inputs": [],
            "elk_outputs": [],
        }

    def project_from_elements(
        self,
        elements: list[CircuitElement],
        name: str = "project",
        source_path: Path | None = None,
    ) -> CircuitProject:
        """Create a CircuitProject from parsed circuit elements."""
        return CircuitProject(elements=list(elements), name=name, source_path=source_path)

    def parse_file(self, file_path: Path) -> StageResult[CircuitProject]:
        """Parse a Circuit JSON file into a CircuitProject."""
        from circuitweaver.io.json import read_circuit

        result: StageResult[CircuitProject] = StageResult(stage="parse")
        try:
            elements = read_circuit(file_path)
        except Exception as e:
            result.add_error("parse_failed", str(e), location={"path": str(file_path)})
            return result

        result.value = self.project_from_elements(
            elements,
            name=file_path.stem,
            source_path=file_path,
        )
        result.artifacts.append(
            OutputArtifact(kind="input_json", path=file_path, name=file_path.name)
        )
        return result

    def validate_project(self, project: CircuitProject) -> StageResult[CircuitProject]:
        """Validate a project and return structured diagnostics."""
        result: StageResult[CircuitProject] = StageResult(stage="validate", value=project)

        if project.source_path:
            from circuitweaver.validator import validate_circuit_file

            validation = validate_circuit_file(project.source_path)
        else:
            from circuitweaver.validator import validate_circuit_elements

            validation = validate_circuit_elements(project.elements)

        for error in validation.errors:
            result.diagnostics.append(
                Diagnostic(
                    severity="error",
                    code=error.rule,
                    message=error.message,
                    element_id=error.element_id,
                    location=error.location,
                    stage="validate",
                )
            )
        for warning in validation.warnings:
            result.diagnostics.append(
                Diagnostic(
                    severity="warning",
                    code=warning.rule,
                    message=warning.message,
                    element_id=warning.element_id,
                    location=warning.location,
                    stage="validate",
                )
            )
        return result

    def layout_project(
        self,
        project: CircuitProject,
        debug_dir: Path | None = None,
        debug_basename: str | None = None,
    ) -> StageResult[CircuitProject]:
        """Run the layout stage and return a project with schematic elements."""
        result: StageResult[CircuitProject] = StageResult(stage="layout")
        try:
            elements = self.layout(
                project.elements,
                debug_dir=debug_dir,
                debug_basename=debug_basename,
            )
        except Exception as e:
            result.add_error("layout_failed", str(e))
            return result

        updated = project.with_elements(elements)
        result.value = updated
        result.artifacts.append(
            OutputArtifact(
                kind="schematic_elements",
                name="schematic",
                metadata={"element_count": len(updated.schematic_elements)},
            )
        )
        for artifact_kind, entries in self.last_layout_artifacts.items():
            for entry in entries:
                result.artifacts.append(
                    OutputArtifact(
                        kind=artifact_kind[:-1],
                        name=str(entry["sheet_id"]),
                        metadata={"sheet_id": entry["sheet_id"], "graph": entry["graph"]},
                    )
                )
        return result

    def schematic_project(self, project: CircuitProject) -> StageResult[CircuitProject]:
        """Ensure the project has schematic elements."""
        completeness = self.schematic_completeness(project)
        if completeness.ok and project.has_schematic_layer():
            result: StageResult[CircuitProject] = StageResult(stage="schematic", value=project)
            result.artifacts.append(
                OutputArtifact(
                    kind="schematic_elements",
                    name="schematic",
                    metadata={"element_count": len(project.schematic_elements)},
                )
            )
            return result
        if project.has_schematic_layer() and not completeness.ok:
            return self.layout_project(project)
        return self.layout_project(project)

    def schematic_completeness(self, project: CircuitProject) -> StageResult[CircuitProject]:
        """Check whether an existing schematic layer covers source components and ports."""
        result: StageResult[CircuitProject] = StageResult(
            stage="schematic_completeness",
            value=project,
        )
        if not project.has_schematic_layer():
            result.add_warning("missing_schematic_layer", "Project has no schematic layer.")
            return result

        schematic_component_sources = {
            e.source_component_id
            for e in project.schematic_elements
            if isinstance(e, SchematicComponent)
        }
        schematic_port_sources = {
            e.source_port_id for e in project.schematic_elements if isinstance(e, SchematicPort)
        }
        missing_components = sorted(set(project.source_components) - schematic_component_sources)
        missing_ports = sorted(set(project.source_ports) - schematic_port_sources)
        if missing_components:
            result.add_error(
                "incomplete_schematic_components",
                f"Schematic layer is missing source components: {', '.join(missing_components)}",
            )
        if missing_ports:
            result.add_error(
                "incomplete_schematic_ports",
                f"Schematic layer is missing source ports: {', '.join(missing_ports)}",
            )
        return result

    def kicad_project(self, project: CircuitProject) -> StageResult[KiCadProject]:
        """Transform schematic elements to in-memory KiCad S-expressions."""
        result: StageResult[KiCadProject] = StageResult(stage="kicad_transform")
        if not project.has_schematic_layer():
            result.add_error(
                "missing_schematic_layer",
                "Project has no schematic elements. Run the schematic/layout stage first.",
            )
            return result

        source_components: dict[str, SourceComponent] = project.source_components
        transform = SchematicToSExprTransform(uuid_factory=self.uuid_factory)
        schematics = {
            sheet_id: transform.transform(project.elements, sheet_id, source_components)
            for sheet_id in project.sheet_ids
        }
        project_content = transform.transform_project(project.name, list(project.sheet_ids))
        result.value = KiCadProject(
            project=project,
            schematics=schematics,
            project_file_content=project_content,
        )
        for sheet_id in sorted(schematics):
            filename = (
                f"{project.name}.kicad_sch" if sheet_id == "root" else f"{sheet_id}.kicad_sch"
            )
            result.artifacts.append(OutputArtifact(kind="kicad_schematic_sexpr", name=filename))
        result.artifacts.append(
            OutputArtifact(kind="kicad_project_json", name=f"{project.name}.kicad_pro")
        )
        return result

    def write_kicad(
        self,
        kicad_project: KiCadProject,
        output_dir: Path,
    ) -> StageResult[Path]:
        """Write in-memory KiCad artifacts to disk."""
        result: StageResult[Path] = StageResult(stage="write")
        output_dir.mkdir(parents=True, exist_ok=True)

        root_sch_file = None
        for sheet_id, sexp in kicad_project.schematics.items():
            if sheet_id == "root":
                filename = f"{kicad_project.project.name}.kicad_sch"
                root_sch_file = output_dir / filename
            else:
                filename = f"{sheet_id}.kicad_sch"
            path = output_dir / filename
            path.write_text(s_expr_serialize(sexp))
            result.artifacts.append(
                OutputArtifact(kind="kicad_schematic", path=path, name=filename)
            )

        pro_filename = f"{kicad_project.project.name}.kicad_pro"
        pro_path = output_dir / pro_filename
        pro_path.write_text(kicad_project.project_file_content)
        result.artifacts.append(
            OutputArtifact(kind="kicad_project", path=pro_path, name=pro_filename)
        )

        if root_sch_file is None:
            result.add_error("missing_root_sheet", "No root schematic was generated.")
            return result
        result.value = root_sch_file
        return result

    def compile(
        self,
        elements: list[CircuitElement],
        output_dir: Path,
        project_name: str = "project",
    ) -> Path:
        """Compile Circuit JSON to KiCad schematic files.

        1. Run auto-layout to generate schematic_* elements if missing.
        2. Transform to S-expressions.
        3. Write .kicad_sch and .kicad_pro files.

        Args:
            elements: List of circuit elements.
            output_dir: Directory to write output files.
            project_name: Name for the KiCad project.

        Returns:
            Path to the root schematic file.
        """
        project = self.project_from_elements(elements, name=project_name)
        schematic_result = self.schematic_project(project)
        if not schematic_result.ok or schematic_result.value is None:
            raise RuntimeError(_format_stage_errors(schematic_result))

        kicad_result = self.kicad_project(schematic_result.value)
        if not kicad_result.ok or kicad_result.value is None:
            raise RuntimeError(_format_stage_errors(kicad_result))

        write_result = self.write_kicad(kicad_result.value, output_dir)
        if not write_result.ok or write_result.value is None:
            raise RuntimeError(_format_stage_errors(write_result))

        for artifact in write_result.artifacts:
            if artifact.path:
                logger.info(f"Wrote {artifact.kind} to {artifact.path}")
        return write_result.value

    def layout(
        self,
        elements: list[CircuitElement],
        debug_dir: Path | None = None,
        debug_basename: str | None = None,
    ) -> list[CircuitElement]:
        """Run auto-layout on source elements.

        Transforms Source elements into positioned Schematic elements.

        Args:
            elements: List of circuit elements.
            debug_dir: Optional directory to write ELK debug files.
            debug_basename: Optional base filename for ELK debug files.

        Returns:
            Elements with added Schematic elements.
        """
        source_components = [e for e in elements if isinstance(e, SourceComponent)]
        source_groups = [e for e in elements if isinstance(e, SourceGroup)]
        source_ports = [e for e in elements if isinstance(e, SourcePort)]
        source_traces = [e for e in elements if isinstance(e, SourceTrace)]
        source_nets = [e for e in elements if isinstance(e, SourceNet)]

        if not source_components:
            return elements
        self.last_layout_artifacts = {"elk_inputs": [], "elk_outputs": []}

        # 1. Map elements to sheets and load symbols
        element_to_sheet, element_to_group = self._map_elements(
            source_components, source_groups, source_ports
        )

        # Use the explicit subcircuit_id when present, otherwise the group ID.
        subcircuit_ids = {self._get_group_sheet_id(g) for g in source_groups if g.is_subcircuit}
        all_sheet_ids = {"root"} | subcircuit_ids
        symbol_map = self._load_symbols(source_components)

        # 2. Connectivity pre-processing
        connectivity_elements, sheet_connectivity = build_connection_plan(
            traces=source_traces,
            ports=source_ports,
            nets=source_nets,
            element_to_sheet=element_to_sheet,
            element_to_group=element_to_group,
            groups=source_groups,
            elements=elements,
            global_resolver=GlobalNetResolver.from_elements(elements),
        )

        final_positioned_elements: list[CircuitElement] = []

        # 3. Process each sheet
        for sheet_id in all_sheet_ids:
            sheet_elements = self._get_sheet_elements(
                elements + connectivity_elements,
                element_to_sheet,
                sheet_id,
            )
            sheet_boxes = [
                g
                for g in source_groups
                if g.is_subcircuit and element_to_sheet.get(g.source_group_id) == sheet_id
            ]

            if not sheet_elements and not sheet_boxes:
                continue

            all_sheet_elements = sheet_elements + sheet_boxes

            # Transform: Source → Layout
            source_to_layout = SourceToLayoutTransform(symbol_map=symbol_map)
            layout_node, registry = source_to_layout.transform(
                sheet_id=sheet_id,
                elements=all_sheet_elements,
                sheet_connectivity=sheet_connectivity,
            )

            # Run ELK auto-router
            elk_dict = layout_node.model_dump()
            self.last_layout_artifacts["elk_inputs"].append(
                {"sheet_id": sheet_id, "graph": elk_dict}
            )
            if DEBUG_ELK or (debug_dir and debug_basename):
                if debug_dir and debug_basename:
                    suffix = "" if sheet_id == "root" else f"_{sheet_id}"
                    debug_dir.joinpath(f"{debug_basename}_layout_in{suffix}.json").write_text(
                        json.dumps(elk_dict, indent=2)
                    )
                else:
                    Path(f"debug_elk_in_{sheet_id}.json").write_text(json.dumps(elk_dict, indent=2))

            layout_results_dict = self.router.run(elk_dict)
            self.last_layout_artifacts["elk_outputs"].append(
                {"sheet_id": sheet_id, "graph": layout_results_dict}
            )

            if DEBUG_ELK or (debug_dir and debug_basename):
                if debug_dir and debug_basename:
                    suffix = "" if sheet_id == "root" else f"_{sheet_id}"
                    debug_dir.joinpath(f"{debug_basename}_layout_out{suffix}.json").write_text(
                        json.dumps(layout_results_dict, indent=2)
                    )
                else:
                    Path(f"debug_elk_out_{sheet_id}.json").write_text(
                        json.dumps(layout_results_dict, indent=2)
                    )

            layout_results = LayoutNode.model_validate(layout_results_dict)

            # Transform: Layout → Schematic
            layout_to_schematic = LayoutToSchematicTransform(symbol_map=symbol_map)
            positioned_elements = layout_to_schematic.transform(
                sheet_id=sheet_id,
                layout_result=layout_results,
                registry=registry,
                elements=all_sheet_elements,
            )
            final_positioned_elements.extend(positioned_elements)

        # Filter to schematic elements only
        schematic_results = [
            e for e in final_positioned_elements if e.type.startswith("schematic_")
        ]

        return elements + connectivity_elements + schematic_results

    def check_layout_quality(
        self,
        elements: list[CircuitElement],
    ) -> LayoutQualityReport:
        """Run layout-quality diagnostics against positioned schematic elements.

        If the input contains only source elements, layout is generated first and
        the resulting schematic elements are checked.
        """
        has_layout = any(e.type.startswith("schematic_") for e in elements)
        checked_elements = elements if has_layout else self.layout(elements)
        source_components = [e for e in checked_elements if isinstance(e, SourceComponent)]
        checker = LayoutQualityChecker(symbol_map=self._load_symbols(source_components))
        return checker.check(checked_elements)

    def _get_sheet_elements(
        self,
        elements: list[CircuitElement],
        element_to_sheet: dict[str, str],
        sheet_id: str,
    ) -> list[CircuitElement]:
        """Get elements belonging to a specific sheet."""
        result = []
        for e in elements:
            if isinstance(e, (SourceTrace, SourceNet)):
                continue

            if hasattr(e, "sheet_id"):
                if e.sheet_id == sheet_id:
                    result.append(e)
            else:
                eid = get_element_id(e)
                if element_to_sheet.get(eid) == sheet_id:
                    result.append(e)

        return result

    def _map_elements(
        self,
        components: list[SourceComponent],
        groups: list[SourceGroup],
        ports: list[SourcePort],
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Map elements to their sheets and groups."""
        element_to_sheet = {}
        element_to_group = {}
        group_map = {g.source_group_id: g for g in groups}
        subcircuit_map = {
            sheet_id: g
            for g in groups
            if g.is_subcircuit and (sheet_id := self._get_group_sheet_id(g))
        }

        def get_owner_sheet(gid: str | None, visited: set[str] | None = None) -> str:
            """Recursively find the subcircuit_id that owns this group."""
            if not gid or gid not in group_map:
                return "root"
            visited = visited or set()
            if gid in visited:
                return "root"
            visited.add(gid)
            g = group_map[gid]
            if g.is_subcircuit:
                return self._get_group_sheet_id(g)
            return get_owner_sheet(g.parent_source_group_id, visited)

        for c in components:
            pid = c.source_group_id or c.subcircuit_id
            # Resolve subcircuit_id to source_group_id if needed
            if pid and pid not in group_map:
                match = subcircuit_map.get(pid)
                if match:
                    pid = match.source_group_id

            sheet = get_owner_sheet(pid)
            element_to_sheet[c.source_component_id] = sheet
            element_to_group[c.source_component_id] = pid or sheet

            for p in ports:
                if p.source_component_id == c.source_component_id:
                    element_to_sheet[p.source_port_id] = sheet

        for g in groups:
            # A group's owner sheet is determined by its parent
            sheet = get_owner_sheet(g.parent_source_group_id, {g.source_group_id})
            element_to_sheet[g.source_group_id] = sheet
            element_to_group[g.source_group_id] = g.parent_source_group_id or sheet

        return element_to_sheet, element_to_group

    @staticmethod
    def _get_group_sheet_id(group: SourceGroup) -> str:
        """Return the schematic sheet ID owned by a subcircuit group."""
        return group.subcircuit_id or group.source_group_id

    def _load_symbols(self, components: list[SourceComponent]) -> dict[str, Any]:
        """Load symbol info for all components."""
        unique_symbols = {}
        for comp in components:
            symbol_id = get_effective_symbol_id(comp)
            if symbol_id and symbol_id not in unique_symbols:
                try:
                    unique_symbols[symbol_id] = self.symbol_lookup(symbol_id)
                except Exception as e:
                    logger.warning(f"Could not load symbol {symbol_id}: {e}")
        return unique_symbols

    def _process_connectivity(
        self,
        traces: list[SourceTrace],
        ports: list[SourcePort],
        nets: list[SourceNet],
        element_to_sheet: dict[str, str],
        element_to_group: dict[str, str],
        _groups: list[SourceGroup],
        elements: list[CircuitElement],
        global_resolver: GlobalNetResolver,
    ) -> tuple[list[CircuitElement], dict[str, list[dict[str, Any]]]]:
        """Compatibility wrapper returning legacy connectivity dictionaries."""
        return build_sheet_connectivity(
            traces=traces,
            ports=ports,
            nets=nets,
            element_to_sheet=element_to_sheet,
            element_to_group=element_to_group,
            groups=_groups,
            elements=elements,
            global_resolver=global_resolver,
        )

    def run_erc(self, schematic_path: Path) -> dict[str, Any]:
        """Run ERC on a generated schematic.

        Args:
            schematic_path: Path to the .kicad_sch file.

        Returns:
            Dict with 'is_valid', 'errors', 'warnings'.
        """
        from circuitweaver.erc.checker import ERCChecker

        if self.erc_runner is not None:
            return self.erc_runner(schematic_path)
        checker = ERCChecker(kicad_cli_path=self.kicad_cli_path)
        return checker.run(schematic_path)
