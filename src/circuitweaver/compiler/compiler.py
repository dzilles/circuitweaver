"""Compiler for Circuit JSON to KiCad schematic with multi-sheet support."""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Set

from circuitweaver.compiler.autolayout import AutoLayoutEngine
from circuitweaver.compiler.kicad_writer import KiCadWriter
from circuitweaver.erc.checker import ERCChecker
from circuitweaver.types.circuit_json import CircuitElement, SourceComponent

logger = logging.getLogger(__name__)


class Compiler:
    """Orchestrates the conversion of Circuit JSON to KiCad files."""

    def __init__(self, helper_path: Optional[str] = None, kicad_cli_path: str = "kicad-cli"):
        self.layout_engine = AutoLayoutEngine(helper_path=helper_path)
        self.writer = KiCadWriter()
        self.erc_checker = ERCChecker(kicad_cli_path=kicad_cli_path)

    def compile(self, elements: List[CircuitElement], output_dir: Path, project_name: str = "project") -> Path:
        """Compile Circuit JSON to KiCad schematic files.
        
        1. Run auto-layout to generate schematic_* elements if missing.
        2. Identify all sheets generated.
        3. Use KiCadWriter to generate multiple .kicad_sch and one .kicad_pro file.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Run Layout
        # Check if we already have schematic layout data
        has_layout = any(e.type.startswith("schematic_") for e in elements)
        
        if not has_layout:
            logger.info("No layout found, running hierarchical auto-layout engine...")
            elements = self.layout_engine.layout(elements)
        else:
            logger.info("Layout found in input, skipping auto-layout.")

        # 2. Identify all sheets generated (including root)
        all_sheet_ids: Set[str] = set()
        for e in elements:
            if hasattr(e, "sheet_id"):
                all_sheet_ids.add(e.sheet_id)
        if not all_sheet_ids:
            all_sheet_ids.add("root")

        # 3. Prepare common context
        source_components: Dict[str, SourceComponent] = {
            e.source_component_id: e for e in elements if isinstance(e, SourceComponent)
        }

        # 4. Write each Schematic file
        root_sch_file = None
        for sheet_id in all_sheet_ids:
            sch_content = self.writer.write_schematic(
                elements, 
                sheet_id=sheet_id,
                source_components=source_components
            )
            
            # Filename logic: root sheet uses project name, others use sheet_id
            if sheet_id == "root":
                filename = f"{project_name}.kicad_sch"
                root_sch_file = output_dir / filename
            else:
                filename = f"{sheet_id}.kicad_sch"
            
            (output_dir / filename).write_text(sch_content)
            logger.info(f"Wrote sheet '{sheet_id}' to {output_dir / filename}")

        # 5. Write Project file linking everything
        pro_content = self.writer.write_project(project_name, list(all_sheet_ids))
        pro_file = output_dir / f"{project_name}.kicad_pro"
        pro_file.write_text(pro_content)
        logger.info(f"Wrote project to {pro_file}")

        return root_sch_file

    def run_erc(self, schematic_path: Path):
        """Run ERC on a generated schematic."""
        return self.erc_checker.run(schematic_path)
