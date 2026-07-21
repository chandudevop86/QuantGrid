from pathlib import Path


IGNORED_DIRECTORIES = {
    ".git",
    ".github",
    "node_modules",
    "venv",
    ".venv",
    "__pycache__",
    "dist",
    "build",
    "coverage",
    ".pytest_cache",
}


IGNORED_FILES = {
    "package-lock.json",
    "yarn.lock",
    "poetry.lock",
}


SUPPORTED_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".java",
    ".go",
}


def should_scan(file_path: str) -> bool:

    path = Path(file_path)

    if path.name in IGNORED_FILES:
        return False

    if path.suffix not in SUPPORTED_EXTENSIONS:
        return False

    for parent in path.parts:
        if parent in IGNORED_DIRECTORIES:
            return False

    return True