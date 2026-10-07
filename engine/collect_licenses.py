from importlib.metadata import distributions
from pathlib import Path
import sys

out = Path(sys.argv[1])
with out.open("w") as target:
    target.write("Bundled engine runtime notices\nPython 3.12, PyInstaller 6.16.0 and installed dependencies\n")
    for path in [Path("/usr/local/LICENSE"), Path("/usr/local/lib/python3.12/LICENSE.txt")]:
        if path.is_file():
            target.write(f"\n=== Python: {path.name} ===\n" + path.read_text(errors="replace") + "\n")
    for distribution in sorted(distributions(), key=lambda d: d.metadata["Name"].lower()):
        target.write(f"\n=== {distribution.metadata['Name']} {distribution.version} ===\n")
        target.write(f"License metadata: {distribution.metadata.get('License', '')}\n")
        for file in distribution.files or []:
            if "license" not in str(file).lower() and "copying" not in file.name.lower():
                continue
            path = distribution.locate_file(file)
            if path.is_file() and path.suffix not in {".py", ".pyc"}:
                target.write(f"\n--- {file} ---\n" + path.read_text(errors="replace") + "\n")
