"""Scaffold metadata and the stdlib-only import boundary are part of PR 1."""

import ast
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "central_heating"


def test_stub_imports_without_home_assistant():
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            "-c",
            "import custom_components.central_heating; "
            "from custom_components.central_heating import demand, smoothing, schedule, storage; "
            "import sys; assert not any(k.startswith('homeassistant') for k in sys.modules)",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_logic_is_stdlib_only():
    for name in ("demand", "smoothing", "schedule"):
        tree = ast.parse((COMPONENT / f"{name}.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] in sys.stdlib_module_names
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                assert node.module.split(".")[0] in sys.stdlib_module_names


def test_scaffold_manifest_and_hacs():
    manifest = json.loads((COMPONENT / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["domain"] == "central_heating"
    assert manifest["config_flow"] is True
    assert manifest["iot_class"] == "calculated"
    assert set(manifest["dependencies"]) == {"http", "frontend", "websocket_api"}
    assert manifest["after_dependencies"] == ["mqtt"]
    assert not manifest.get("requirements")
    assert json.loads((ROOT / "hacs.json").read_text(encoding="utf-8")) == {
        "name": "Central Heating",
        "render_readme": True,
        "homeassistant": "2026.10.0",
    }
    assert (ROOT / ".forgejo" / "workflows" / "ci.yml").is_file()
    assert not (ROOT / ".github").exists()


def test_manifest_hassfest_order_and_issue_tracker():
    manifest = json.loads((COMPONENT / "manifest.json").read_text(encoding="utf-8"))
    assert list(manifest) == ["domain", "name", *sorted(set(manifest) - {"domain", "name"})]
    assert manifest["issue_tracker"] == manifest["documentation"] + "/issues"
