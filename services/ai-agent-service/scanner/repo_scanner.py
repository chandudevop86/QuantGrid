import os


IGNORE = {
    ".git",
    "venv",
    "__pycache__"
}


def scan_repository(path):

    files=[]


    for root,dirs,names in os.walk(path):

        dirs[:] = [
            d for d in dirs 
            if d not in IGNORE
        ]


        for file in names:

            files.append(
                os.path.join(
                    root,
                    file
                )
            )


    return files