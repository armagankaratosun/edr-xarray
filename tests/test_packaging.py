"""Tests for packaging and release workflow configuration."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_sdist_includes_only_documented_examples_and_public_project_files() -> None:
    """The source distribution should include public project files only."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    sdist = pyproject["tool"]["hatch"]["build"]["targets"]["sdist"]
    only_include = set(sdist["only-include"])

    assert {
        "examples/01_quickstart.ipynb",
        "examples/02_indexing_and_fetching.ipynb",
        "examples/03_backend_options.ipynb",
        "examples/README.md",
    } <= only_include
    assert "examples" not in only_include
    assert not any(path.startswith("examples/99_") for path in only_include)
    assert {"AGENTS.md", "plans", "uv.lock"}.isdisjoint(only_include)


def test_python_support_metadata_matches_ci_matrix() -> None:
    """Python support metadata should match the versions run in CI."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    classifiers = set(pyproject["project"]["classifiers"])

    assert pyproject["project"]["requires-python"] == ">=3.11,<3.13"
    assert "Programming Language :: Python :: 3.11" in classifiers
    assert "Programming Language :: Python :: 3.12" in classifiers
    assert "Programming Language :: Python :: 3.13" not in classifiers


def test_project_urls_include_repository_issues_and_changelog() -> None:
    """Project URLs should expose repository, issue, and changelog links."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    urls = pyproject["project"]["urls"]

    assert {"Repository", "Issues", "Changelog"} <= set(urls)


def test_tracked_example_notebooks_use_placeholder_server_and_clear_outputs() -> None:
    """Committed notebooks should be editable examples without saved outputs."""
    for path in (
        ROOT / "examples" / "01_quickstart.ipynb",
        ROOT / "examples" / "02_indexing_and_fetching.ipynb",
        ROOT / "examples" / "03_backend_options.ipynb",
    ):
        text = path.read_text()
        notebook = json.loads(text)
        sources = "\n".join("".join(cell.get("source", [])) for cell in notebook["cells"])

        assert 'server = "https://edr.example.com"' in sources
        assert "127.0.0.1" not in sources
        assert "localhost" not in sources
        assert "%pip install -q -e" not in sources
        assert "edr-xarray" in sources
        for cell in notebook["cells"]:
            if cell.get("cell_type") == "code":
                assert cell["execution_count"] is None
                assert cell["outputs"] == []


def test_publish_workflow_runs_quality_gate_before_publish() -> None:
    """Publishing should depend on the same quality gate as CI."""
    workflow = (ROOT / ".github" / "workflows" / "publish.yml").read_text()

    assert "quality-gate:" in workflow
    assert 'python-version: ["3.11", "3.12"]' in workflow
    assert "needs: quality-gate" in workflow
    assert "uv run pyright --verifytypes edr_xarray --ignoreexternal" in workflow


def test_publish_workflow_stages_only_distribution_artifacts() -> None:
    """Publishing should stage only wheel and sdist artifacts."""
    workflow = (ROOT / ".github" / "workflows" / "publish.yml").read_text()

    assert "mkdir -p dist-pypi" in workflow
    assert "cp dist/*.tar.gz dist/*.whl dist-pypi/" in workflow
    assert "uvx twine check dist-pypi/*" in workflow
    assert "packages-dir: dist-pypi/" in workflow
