"""Safe syntax smoke tests: never load the Flask app or touch real data."""

import ast
import shutil
import subprocess
from pathlib import Path

import pytest
from jinja2 import Environment

ROOT = Path(__file__).resolve().parents[1]
WEBAPP = ROOT / "skin_cancer" / "webapp"


def test_python_sources_parse_without_importing_app():
    sources = sorted(p for p in ROOT.rglob("*.py") if ".git" not in p.parts)
    assert sources
    for source in sources:
        ast.parse(source.read_text(encoding="utf-8"), filename=str(source))


def test_jinja_templates_parse_without_rendering_real_data():
    templates = sorted((WEBAPP / "templates").rglob("*.html"))
    assert templates
    environment = Environment()
    for source in templates:
        environment.parse(source.read_text(encoding="utf-8"))


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_javascript_syntax_without_starting_services():
    scripts = sorted((WEBAPP / "static" / "js").glob("*.js"))
    assert scripts
    for source in scripts:
        completed = subprocess.run(
            ["node", "--check", str(source)],
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
        )
        assert completed.returncode == 0, f"{source}: {completed.stderr}"
