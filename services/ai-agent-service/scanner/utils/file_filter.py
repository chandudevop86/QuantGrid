from pathlib import Path


def is_terraform_resource_file(file_path: str) -> bool:
    path = Path(file_path)

    if path.suffix != ".tf":
        return False

    name = path.name.lower()

    ignore = {
        "variables.tf",
        "outputs.tf",
        "versions.tf",
        "providers.tf",
        "locals.tf",
    }

    if name in ignore:
        return False

    return True