from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = PROJECT_ROOT / "docs"
NOTEBOOKS_DIR = DOCS_DIR / "notebooks"
NOTEBOOK_SOURCE_DIR = DOCS_DIR / "notebook_sources"


def notebook(cells: list[dict], *, title: str) -> dict:
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.12"},
            "title": title,
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def md_cell(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def code_cell(text: str) -> dict:
    return {
        "cell_type": "code",
        "metadata": {},
        "execution_count": None,
        "outputs": [],
        "source": text.splitlines(keepends=True),
    }


def write_notebook(path: Path, cells: list[dict], *, title: str) -> None:
    path.write_text(
        json.dumps(notebook(cells, title=title), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def convert_markdown_copy(markdown_path: Path, notebook_path: Path, title: str) -> None:
    cells = [
        md_cell(f"# {title}\n\nCopia em notebook de `{markdown_path.relative_to(PROJECT_ROOT)}`.\n"),
        md_cell(markdown_path.read_text(encoding="utf-8")),
    ]
    write_notebook(notebook_path, cells, title=title)


def main() -> None:
    NOTEBOOKS_DIR.mkdir(parents=True, exist_ok=True)

    convert_markdown_copy(
        DOCS_DIR / "architecture.md",
        NOTEBOOKS_DIR / "00_architecture.ipynb",
        "Architecture Notes",
    )
    convert_markdown_copy(
        DOCS_DIR / "mvp_scope.md",
        NOTEBOOKS_DIR / "01_mvp_scope.ipynb",
        "MVP Scope",
    )
    convert_markdown_copy(
        DOCS_DIR / "study_manifest_contract.md",
        NOTEBOOKS_DIR / "07_study_manifest_contract.ipynb",
        "Study Manifest Contract",
    )
    convert_markdown_copy(
        DOCS_DIR / "proposals_radar.md",
        NOTEBOOKS_DIR / "08_proposals_radar.ipynb",
        "Proposals Radar",
    )
    convert_markdown_copy(
        DOCS_DIR / "change_map_20260415.md",
        NOTEBOOKS_DIR / "09_change_map_20260415.ipynb",
        "Change Map 2026-04-15",
    )
    convert_markdown_copy(
        DOCS_DIR / "simulated_annealing_contract.md",
        NOTEBOOKS_DIR / "10_simulated_annealing_contract.ipynb",
        "Simulated Annealing Contract",
    )

    notebooks = {
        "02_repository_reference.ipynb": {
            "title": "Repository Reference",
            "markdown_path": NOTEBOOK_SOURCE_DIR / "02_repository_reference.md",
            "code": (
                "from pathlib import Path\n"
                "root = next(path for path in [Path.cwd(), *Path.cwd().parents] if (path / 'pyproject.toml').exists())\n"
                "files = [p.relative_to(root) for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts]\n"
                "files[:80]"
            ),
        },
        "03_engine_operations_and_calculations.ipynb": {
            "title": "Engine Operations and Calculations",
            "markdown_path": NOTEBOOK_SOURCE_DIR / "03_engine_operations_and_calculations.md",
            "code": (
                "from pathlib import Path\n"
                "root = next(path for path in [Path.cwd(), *Path.cwd().parents] if (path / 'pyproject.toml').exists())\n"
                "import sys\n"
                "if str(root) not in sys.path:\n"
                "    sys.path.insert(0, str(root))\n"
                "from policy_lab.storage.studies_repository import StudyRepository\n"
                "from policy_lab.storage.feature_repository import FeatureRepository\n"
                "from policy_lab.storage.result_repository import ResultRepository\n"
                "from policy_lab.storage.scenario_repository import ScenarioRepository\n"
                "from policy_lab.engine.scenario_orchestrator import ScenarioOrchestrator\n"
                "study_repo = StudyRepository()\n"
                "orchestrator = ScenarioOrchestrator(study_repo, FeatureRepository(), ScenarioRepository(), ResultRepository())\n"
                "study = study_repo.load('demo_lending')\n"
                "baseline = orchestrator.run_baseline(study)\n"
                "baseline.result.metrics"
            ),
        },
        "04_app_and_user_workflows.ipynb": {
            "title": "App and User Workflows",
            "markdown_path": NOTEBOOK_SOURCE_DIR / "04_app_and_user_workflows.md",
            "code": (
                "from pathlib import Path\n"
                "root = next(path for path in [Path.cwd(), *Path.cwd().parents] if (path / 'pyproject.toml').exists())\n"
                "app_path = root / 'policy_lab/apps/simulator_app/app.py'\n"
                "print(app_path)\n"
                "print(app_path.read_text(encoding='utf-8')[:2000])"
            ),
        },
        "05_data_study_and_policy_contract.ipynb": {
            "title": "Data Study and Policy Contract",
            "markdown_path": NOTEBOOK_SOURCE_DIR / "05_data_study_and_policy_contract.md",
            "code": (
                "import csv\n"
                "from pathlib import Path\n"
                "root = next(path for path in [Path.cwd(), *Path.cwd().parents] if (path / 'pyproject.toml').exists())\n"
                "snapshot = root / 'runtime/studies/demo_lending/study_snapshot.csv'\n"
                "with snapshot.open(encoding='utf-8') as handle:\n"
                "    reader = csv.DictReader(handle)\n"
                "    rows = [next(reader) for _ in range(5)]\n"
                "rows"
            ),
        },
        "06_development_governance_phases.ipynb": {
            "title": "Development Governance and Phases",
            "markdown_path": NOTEBOOK_SOURCE_DIR / "06_development_governance_phases.md",
            "code": (
                "from pathlib import Path\n"
                "root = next(path for path in [Path.cwd(), *Path.cwd().parents] if (path / 'pyproject.toml').exists())\n"
                "docs = sorted((root / 'docs/notebooks').glob('*.ipynb'))\n"
                "[doc.name for doc in docs]"
            ),
        },
    }

    for file_name, payload in notebooks.items():
        cells = [
            md_cell(payload["markdown_path"].read_text(encoding="utf-8")),
            code_cell(payload["code"]),
        ]
        write_notebook(NOTEBOOKS_DIR / file_name, cells, title=payload["title"])

    (NOTEBOOKS_DIR / "README.md").write_text(
        "# Documentacao em Notebook\n\n"
        "1. `00_architecture.ipynb`\n"
        "2. `01_mvp_scope.ipynb`\n"
        "3. `02_repository_reference.ipynb`\n"
        "4. `03_engine_operations_and_calculations.ipynb`\n"
        "5. `04_app_and_user_workflows.ipynb`\n"
        "6. `05_data_study_and_policy_contract.ipynb`\n"
        "7. `06_development_governance_phases.ipynb`\n"
        "8. `07_study_manifest_contract.ipynb`\n"
        "9. `08_proposals_radar.ipynb`\n"
        "10. `09_change_map_20260415.ipynb`\n",
        "11. `10_simulated_annealing_contract.ipynb`\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
