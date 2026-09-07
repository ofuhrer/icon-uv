"""Inspect release assets and smoke-test the wheel outside the source tree."""

import argparse
from pathlib import Path
import subprocess
import tarfile
import tempfile
import zipfile


SMOKE = """
from pathlib import Path
import icon_uv
from icon_uv.radiation import RadiationTable
from icon_uv.schema import SCHEMA_VERSIONS, load_schema

assert 'site-packages' in str(Path(icon_uv.__file__).resolve())
for version in SCHEMA_VERSIONS:
    assert load_schema(version)['properties']['schema_version']['const'] == version
table = RadiationTable()
assert table.sha256 == 'a33db2d4b2806f216eef356c761460383bb4a9fca53e3b958715bc12e6d6dcba'
assert table.at(30, 310, 95000, .12, .05, 0)[..., 2:].sum() > 0
print('Isolated wheel imports and bundled schemas/radiation table: OK')
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    wheels = list(args.directory.glob("*.whl"))
    sources = list(args.directory.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sources) != 1:
        parser.error("Expected exactly one wheel and one source archive; use a clean output directory")
    wheel = wheels[0].resolve()
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        assert "icon_uv/data/rt.npz" in names
        assert all(f"icon_uv/data/daily-uv-v{version}.schema.json" in names for version in (1, 2, 3, 4))
    with tarfile.open(sources[0]) as archive:
        names = {name.split("/", 1)[-1] for name in archive.getnames()}
        assert {"docs/images/uv-map.gif", "docs/validation-manifest.json", "examples/offline.py", "tools/generate_schemas.py",
                "tools/check_distribution.py", "tests/test_schema_helpers.py"} <= names
    with tempfile.TemporaryDirectory(prefix="icon-uv-wheel-") as directory:
        subprocess.run(["uv", "run", "--isolated", "--no-project", "--with", str(wheel),
                        "python", "-c", SMOKE], cwd=directory, check=True)


if __name__ == "__main__":
    main()
