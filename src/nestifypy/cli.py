"""
nestifypy.cli
----------
CLI entry point for the Nestifypy ecosystem.
Registered via pyproject.toml: nestifypy = "nestifypy.cli:main"
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(
    name="nestifypy",
    help="Nestifypy — Modern utility and game framework for Python",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

# ─────────────────────────────────────────────────────────────────────────────
#  Default project.yml template
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_PROJECT_YML = """\
project:
  name: "{name}"
  version: "0.1.0"
  description: ""

python:
  version: "{python_version}"

build:
  backend: "uv"

docker:
  image: "{name}:latest"
"""

_DEFAULT_PYPROJECT = """\
[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "{name}"
version = "0.1.0"
description = ""
requires-python = ">={python_version}"
dependencies = [
    "nestifypy>=0.1.0"
]

[project.optional-dependencies]
dev = [
    "ruff>=0.4",
    "pytest>=8.0",
    "mypy>=1.10"
]

[project.scripts]
{name} = "{name}.cli:main"

[tool.ruff]
line-length = 88
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
addopts = "-v"
"""

_DEFAULT_GITIGNORE = """\
# Byte-compiled / optimized / DLL files
__pycache__/
*.py[cod]
*$py.class

# C extensions
*.so

# Distribution / packaging
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
share/python-wheels/
*.egg-info/
.installed.cfg
*.egg
MANIFEST

# PyInstaller
#  Usually these files are written by a python script from a template
#  before PyInstaller builds the exe, so as to inject date/other infos into it.
*.manifest
*.spec

# Installer logs
pip-log.txt
pip-delete-this-directory.txt

# Unit test / coverage reports
htmlcov/
.tox/
.nox/
.coverage
.coverage.*
.cache
nosetests.xml
coverage.xml
*.cover
*.py,cover
.hypothesis/
.pytest_cache/
cover/

# Translations
*.mo
*.pot

# Django stuff:
*.log
local_settings.py
db.sqlite3
db.sqlite3-journal

# Flask stuff:
instance/
.webassets-cache

# Scrapy stuff:
.scrapy

# Sphinx documentation
docs/_build/

# PyBuilder
.pybuilder/
target/

# Jupyter Notebook
.ipynb_checkpoints

# IPython
profile_default/
ipython_config.py

# PEP 582; used by e.g. github.com/David-OConnor/pyflow
__pypackages__/

# Celery stuff
celerybeat-schedule
celerybeat.pid

# SageMath parsed files
*.sage.py

# Environments
.env
.venv
env/
venv/
ENV/
env.bak/
venv.bak/

# Spyder project settings
.spyderproject
.spyproject

# Rope project settings
.ropeproject

# mkdocs documentation
/site

# mypy
.mypy_cache/
.dmypy.json
dmypy.json

# Pyre type checker
.pyre/

# pytype static type analyzer
.pytype/

# Cython debug symbols
cython_debug/

# IDEs / Editors
.idea/
.vscode/
*.swp
*.swo
*~
.DS_Store

# PyNest specific / local files
.nestifypy/
"""

_DEFAULT_MAIN = """\
from nestifypy.slogger import Logger
from nestifypy.env import Env

def main() -> None:
    Env.load()
    Logger.info("Hello from {name}! Environment loaded successfully.")

if __name__ == "__main__":
    main()
"""


# ─────────────────────────────────────────────────────────────────────────────
#  init
# ─────────────────────────────────────────────────────────────────────────────

@app.command()
def init(
    name: Optional[str] = typer.Option(
        None, "--name", "-n", help="Project name"
    ),
    python: str = typer.Option(
        "3.11", "--python", "-p", help="Python version"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite existing files"
    ),
) -> None:
    """Initialize a new Nestifypy project in the current directory."""

    # Resolve project name
    if name is None:
        name = Path.cwd().name

    typer.echo(f"\n🪺  Initializing Nestifypy project: [bold]{name}[/bold]\n", color=True)

    files = {
        "project.yml":  _DEFAULT_PROJECT_YML.format(name=name, python_version=python),
        "pyproject.toml": _DEFAULT_PYPROJECT.format(name=name, python_version=python),
        ".gitignore": _DEFAULT_GITIGNORE,
        ".python-version": python,
        f"src/{name}/__init__.py": "",
        f"src/{name}/main.py": _DEFAULT_MAIN.format(name=name),
        "tests/__init__.py": "",
    }

    created = []
    skipped = []

    for filepath, content in files.items():
        p = Path(filepath)
        if p.exists() and not force:
            skipped.append(filepath)
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        created.append(filepath)

    for f in created:
        typer.echo(f"  ✓  created  {f}")
    for f in skipped:
        typer.echo(f"  –  skipped  {f}  (use --force to overwrite)")

    typer.echo(f"\n✅  Project [bold]{name}[/bold] ready!\n")
    typer.echo("  Next steps:")
    typer.echo("    uv sync")
    typer.echo("    nestifypy run\n")


# ─────────────────────────────────────────────────────────────────────────────
#  sync
# ─────────────────────────────────────────────────────────────────────────────

@app.command()
def sync(
    config: str = typer.Option("project.yml", "--config", "-c", help="Config file"),
) -> None:
    """Sync pyproject.toml, .python-version, and Docker files from project.yml."""

    try:
        import yaml
    except ImportError:
        typer.echo("❌  pyyaml not installed. Run: pip install pyyaml")
        raise typer.Exit(1)

    cfg_path = Path(config)
    if not cfg_path.exists():
        typer.echo(f"❌  Config file not found: {config}")
        raise typer.Exit(1)

    with open(cfg_path, "r") as f:
        cfg = yaml.safe_load(f)

    python_version: str = str(cfg.get("python", {}).get("version", "3.11"))
    project_name: str = cfg.get("project", {}).get("name", "project")
    project_version: str = cfg.get("project", {}).get("version", "0.1.0")

    typer.echo(f"\n🔄  Syncing from {config}…\n")

    # .python-version
    pv_path = Path(".python-version")
    pv_path.write_text(python_version)
    typer.echo(f"  ✓  .python-version → {python_version}")

    # pyproject.toml
    pp_path = Path("pyproject.toml")
    if pp_path.exists():
        content = pp_path.read_text(encoding="utf-8")
        content = re.sub(
            r'requires-python\s*=\s*"[^"]+"',
            f'requires-python = ">={python_version}"',
            content,
        )
        content = re.sub(
            r'^version\s*=\s*"[^"]+"',
            f'version = "{project_version}"',
            content,
            flags=re.MULTILINE,
        )
        pp_path.write_text(content, encoding="utf-8")
        typer.echo(f"  ✓  pyproject.toml → version={project_version}, python>={python_version}")

    typer.echo(f"\n✅  Sync complete.\n")


# ─────────────────────────────────────────────────────────────────────────────
#  run
# ─────────────────────────────────────────────────────────────────────────────

@app.command()
def run(
    entry: str = typer.Option("main.py", "--entry", "-e", help="Entry file to run"),
    module: Optional[str] = typer.Option(None, "--module", "-m", help="Module to run"),
) -> None:
    """Run the project entry point."""
    import subprocess

    if module:
        typer.echo(f"\n▶  Running module: {module}\n")
        subprocess.run([sys.executable, "-m", module], check=False)
    else:
        entry_path = Path(entry)
        if not entry_path.exists():
            # Try src/<name>/main.py
            candidates = list(Path("src").rglob("main.py")) if Path("src").exists() else []
            if candidates:
                entry_path = candidates[0]
            else:
                typer.echo(f"❌  Entry file not found: {entry}")
                raise typer.Exit(1)
        typer.echo(f"\n▶  Running: {entry_path}\n")
        subprocess.run([sys.executable, str(entry_path)], check=False)


# ─────────────────────────────────────────────────────────────────────────────
#  build
# ─────────────────────────────────────────────────────────────────────────────

@app.command()
def build(
    output: str = typer.Option("dist/", "--output", "-o", help="Output directory"),
) -> None:
    """Build the project distribution."""
    import subprocess

    typer.echo(f"\n📦  Building project…\n")
    result = subprocess.run(
        [sys.executable, "-m", "build", "--outdir", output],
        capture_output=False,
    )
    if result.returncode == 0:
        typer.echo(f"\n✅  Build complete → {output}\n")
    else:
        typer.echo("\n❌  Build failed.\n")
        raise typer.Exit(result.returncode)


# ─────────────────────────────────────────────────────────────────────────────
#  doctor
# ─────────────────────────────────────────────────────────────────────────────

@app.command()
def doctor() -> None:
    """Check environment health and installed dependencies."""
    import importlib
    import platform

    typer.echo("\n🩺  Nestifypy Doctor\n")

    typer.echo(f"  Python     : {platform.python_version()}")
    typer.echo(f"  Platform   : {platform.system()} {platform.machine()}")
    typer.echo(f"  Executable : {sys.executable}\n")

    deps = [
        ("pyyaml",       "yaml"),
        ("python-dotenv","dotenv"),
        ("typer",        "typer"),
        ("watchdog",     "watchdog"),
        ("pygame",       "pygame"),
        ("ruff",         "ruff"),
        ("pytest",       "pytest"),
        ("mypy",         "mypy"),
    ]

    for display_name, import_name in deps:
        try:
            mod = importlib.import_module(import_name)
            version = getattr(mod, "__version__", "?")
            typer.echo(f"  ✓  {display_name:<20} {version}")
        except ImportError:
            typer.echo(f"  –  {display_name:<20} not installed")

    # Check project.yml
    typer.echo()
    if Path("project.yml").exists():
        typer.echo("  ✓  project.yml found")
    else:
        typer.echo("  –  project.yml not found  (run: nestifypy init)")

    typer.echo()


# ─────────────────────────────────────────────────────────────────────────────
#  clean
# ─────────────────────────────────────────────────────────────────────────────

@app.command()
def clean() -> None:
    """Remove build artifacts and caches."""
    import shutil

    targets = [
        "dist", "build", ".nestifypy",
        "__pycache__", ".mypy_cache", ".ruff_cache",
    ]
    removed = []
    for target in targets:
        for p in Path(".").rglob(target):
            if p.is_dir():
                shutil.rmtree(p)
                removed.append(str(p))

    if removed:
        for r in removed:
            typer.echo(f"  🗑  removed {r}")
        typer.echo(f"\n✅  Cleaned {len(removed)} items.\n")
    else:
        typer.echo("  Nothing to clean.")


# ─────────────────────────────────────────────────────────────────────────────
#  info
# ─────────────────────────────────────────────────────────────────────────────

@app.command()
def info() -> None:
    """Show project info from project.yml."""
    try:
        import yaml
        cfg_path = Path("project.yml")
        if not cfg_path.exists():
            typer.echo("❌  project.yml not found. Run: nestifypy init")
            raise typer.Exit(1)
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f)

        typer.echo("\n🪺  Nestifypy Project Info\n")
        proj = cfg.get("project", {})
        typer.echo(f"  Name        : {proj.get('name', '-')}")
        typer.echo(f"  Version     : {proj.get('version', '-')}")
        typer.echo(f"  Description : {proj.get('description', '-')}")
        typer.echo(f"  Python      : {cfg.get('python', {}).get('version', '-')}")
        typer.echo(f"  Build       : {cfg.get('build', {}).get('backend', '-')}")
        typer.echo()
    except ImportError:
        typer.echo("❌  pyyaml required: pip install pyyaml")
        raise typer.Exit(1)


# ─────────────────────────────────────────────────────────────────────────────
#  Entry
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    app()


if __name__ == "__main__":
    main()
