import ast
import sys
from pathlib import Path


def test_domain_layer_has_zero_outer_or_third_party_imports() -> None:
    domain_root = Path(__file__).resolve().parents[2] / "src" / "domain"
    py_files = sorted(domain_root.rglob("*.py"))
    assert py_files, "Expected Python files in src/domain"

    stdlib_modules = sys.stdlib_module_names
    forbidden: list[str] = []

    for path in py_files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top not in stdlib_modules and not alias.name.startswith("src.domain"):
                        forbidden.append(f"{path.name}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                top = node.module.split(".")[0]
                if top not in stdlib_modules and not node.module.startswith("src.domain"):
                    forbidden.append(f"{path.name}: from {node.module} import ...")

    assert not forbidden, f"Domain layer violated Dependency Rule: {forbidden}"
