from scanner.repo_scanner import scan_repository


class ScanContext:

    def __init__(self, repository: str):

        self.repository = repository

        self.files = scan_repository(repository)

        self.python_files = [
            f for f in self.files
            if f.endswith(".py")
        ]

        self.yaml_files = [
            f for f in self.files
            if f.endswith((".yaml", ".yml"))
        ]

        self.terraform_files = [
            f for f in self.files
            if f.endswith(".tf")
        ]

        self.javascript_files = [
            f for f in self.files
            if f.endswith(
                (".js", ".ts", ".tsx")
            )
        ]

        self.shell_files = [
            f for f in self.files
            if f.endswith(".sh")
        ]
