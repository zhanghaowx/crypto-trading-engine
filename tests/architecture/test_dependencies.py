"""The dependency directions AGENTS.md declares, enforced.

Read out of the source rather than by importing it: an import that is
only reached at runtime, inside a function, still creates the dependency
and still has to obey the rules.
"""

import ast
import pathlib

SOURCE_ROOT = pathlib.Path(__file__).resolve().parents[2] / "jolteon"

# Python source is UTF-8 whatever the machine reading it prefers, and this
# suite also runs on Windows, where the default is cp1252 - which cannot
# decode every byte these files contain.
ENCODING = "utf-8"

# Which top-level packages a package may not reach into, and why, in the
# words the failure is reported with.
FORBIDDEN = {
    "engine": {
        "dashboard": "the engine must run with nothing looking at it",
        "cli": "the engine must not depend on how it was started",
        "analysis": "the engine records; it does not analyse",
    },
    "analysis": {
        "dashboard": "an analysis must run outside Streamlit",
        "cli": "an analysis is not a process entrypoint",
    },
    "cli": {
        "dashboard": "starting an engine must not pull in the dashboard",
    },
}


def _imported_packages(source: pathlib.Path) -> set[str]:
    """Every `jolteon.<package>` the module reaches for, at any depth."""
    tree = ast.parse(source.read_text(ENCODING), filename=str(source))
    reached = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            # A relative import cannot leave its own package.
            names = [node.module] if node.level == 0 and node.module else []
        else:
            continue
        for name in names:
            parts = name.split(".")
            if len(parts) >= 2 and parts[0] == "jolteon":
                reached.add(parts[1])
    return reached


def _modules_of(package: str) -> list[pathlib.Path]:
    return sorted((SOURCE_ROOT / package).rglob("*.py"))


def test_no_package_reaches_where_it_may_not():
    violations = []
    for package, forbidden in FORBIDDEN.items():
        for source in _modules_of(package):
            for reached in sorted(_imported_packages(source) & set(forbidden)):
                violations.append(
                    f"{source.relative_to(SOURCE_ROOT.parent)} imports "
                    f"jolteon.{reached}: {forbidden[reached]}."
                )

    assert not violations, (
        "Architecture violation:\n\n"
        + "\n".join(violations)
        + "\n\nSee AGENTS.md for the dependency rules."
    )


def test_every_package_the_rules_name_is_really_there():
    """A package renamed out from under these rules would otherwise leave
    them passing over nothing at all."""
    named = set(FORBIDDEN) | {
        reached for rules in FORBIDDEN.values() for reached in rules
    }

    for package in sorted(named):
        assert (SOURCE_ROOT / package / "__init__.py").is_file(), package


def test_the_dashboard_only_reads_an_engine_recording():
    """The engine owns the file it records into. A dashboard that wrote
    to it would be a second writer of a database another process holds
    open, and the schema would have two owners.
    """
    written = []
    for source in _modules_of("dashboard"):
        text = source.read_text(ENCODING).upper()
        for statement in ("CREATE INDEX", "CREATE TABLE", "INSERT INTO"):
            if statement in text:
                written.append(
                    f"{source.relative_to(SOURCE_ROOT.parent)} runs "
                    f"{statement} against a recording."
                )

    assert not written, (
        "Architecture violation:\n\n"
        + "\n".join(written)
        + "\n\nThe dashboard reads recordings; the engine writes them. "
        "See AGENTS.md."
    )
