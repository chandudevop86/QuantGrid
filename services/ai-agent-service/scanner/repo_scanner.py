from pathlib import Path
import os

EXCLUDED_DIRS = {
    ".git",
    ".github",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".turbo",
    ".idea",
    ".vscode",
    ".terraform",
    "coverage",
    "htmlcov",
    ".cache",
    "logs",
    "tmp",
    "temp"
}

SUPPORTED_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".java",
    ".go",
    ".tf",
    ".yaml",
    ".yml",
    ".json",
    ".sh"
}


def scan_repository(path: str):
    """
    Recursively scan a repository and return supported source files,
    skipping generated, dependency, cache, and build directories.
    """

    repository = Path(path)

    if not repository.exists():
        raise FileNotFoundError(f"Repository not found: {path}")

    files = []

    for root, dirs, filenames in os.walk(repository):

        # Skip excluded directories
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]

        for filename in filenames:

            file_path = Path(root) / filename

            if file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                files.append(str(file_path))

    return sorted(files)