#!/usr/bin/env python3

import os
import hashlib
import ast
import json
from collections import defaultdict
from pathlib import Path


IGNORE_DIRS = {
    ".git",
    "__pycache__",
    "venv",
    ".venv",
    "node_modules"
}


class DuplicateFinder:

    def __init__(self, root):
        self.root = Path(root)

        self.file_hashes = defaultdict(list)
        self.function_hashes = defaultdict(list)
        self.backups = []



    def sha256(self, file):

        h = hashlib.sha256()

        try:
            with open(file, "rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(chunk)

            return h.hexdigest()

        except Exception:
            return None



    def scan_files(self):

        print("[+] Scanning duplicate files")

        for path in self.root.rglob("*"):

            if not path.is_file():
                continue

            if any(x in path.parts for x in IGNORE_DIRS):
                continue


            if "backup" in path.name.lower():
                self.backups.append(str(path))


            digest = self.sha256(path)

            if digest:
                self.file_hashes[digest].append(str(path))



    def normalize_function(self, node):

        try:
            return ast.dump(
                node,
                annotate_fields=False,
                include_attributes=False
            )

        except Exception:
            return None



    def scan_python_functions(self):

        print("[+] Scanning duplicate functions/classes")


        for file in self.root.rglob("*.py"):

            if any(x in file.parts for x in IGNORE_DIRS):
                continue


            try:

                source = file.read_text(
                    encoding="utf-8",
                    errors="ignore"
                )

                tree = ast.parse(source)


                for node in ast.walk(tree):

                    if isinstance(
                        node,
                        (
                            ast.FunctionDef,
                            ast.AsyncFunctionDef,
                            ast.ClassDef
                        )
                    ):

                        signature = self.normalize_function(node)

                        if signature:

                            self.function_hashes[signature].append(
                                f"{file}:{node.name}"
                            )


            except Exception:
                pass



    def report(self):

        result = {

            "duplicate_files": {},

            "duplicate_functions": {},

            "backup_files": self.backups

        }


        for h, files in self.file_hashes.items():

            if len(files) > 1:

                result["duplicate_files"][h] = files



        for h, funcs in self.function_hashes.items():

            if len(funcs) > 1:

                result["duplicate_functions"][h] = funcs



        with open(
            "duplicate_report.json",
            "w"
        ) as f:

            json.dump(
                result,
                f,
                indent=4
            )


        print("\n========== REPORT ==========")

        print(
            "Duplicate files:",
            len(result["duplicate_files"])
        )

        print(
            "Duplicate functions/classes:",
            len(result["duplicate_functions"])
        )

        print(
            "Backup files:",
            len(result["backup_files"])
        )


        print(
            "\nSaved: duplicate_report.json"
        )



if __name__ == "__main__":

    import sys


    target = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "."
    )


    finder = DuplicateFinder(target)

    finder.scan_files()

    finder.scan_python_functions()

    finder.report()