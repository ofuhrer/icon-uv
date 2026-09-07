"""Inspect release assets and smoke-test the wheel outside the source tree."""

import argparse
from email.parser import BytesParser
from pathlib import Path
import subprocess
import tarfile
import tempfile
import tomllib
import zipfile


SMOKE = """
from pathlib import Path
from importlib.metadata import version
import icon_uv
from icon_uv.radiation import RadiationTable
from icon_uv.schema import SCHEMA_VERSIONS, load_schema

assert 'site-packages' in str(Path(icon_uv.__file__).resolve())
assert icon_uv.__version__ == version('icon-uv')
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
    parser.add_argument("--tag", help="Require a release tag matching the package version, e.g. v0.1.0")
    args = parser.parse_args()
    wheels = list(args.directory.glob("*.whl"))
    sources = list(args.directory.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sources) != 1:
        parser.error("Expected exactly one wheel and one source archive; use a clean output directory")
    wheel = wheels[0].resolve()
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        metadata_path, = (name for name in names if name.endswith('.dist-info/METADATA'))
        metadata = BytesParser().parsebytes(archive.read(metadata_path))
        assert metadata['Name'] == 'icon-uv'
        if args.tag and args.tag != f"v{metadata['Version']}":
            parser.error(f"Tag {args.tag!r} does not match package version {metadata['Version']}")
        assert "icon_uv/data/rt.npz" in names
        assert all(f"icon_uv/data/daily-uv-v{version}.schema.json" in names for version in (1, 2, 3, 4, 5))
    with tarfile.open(sources[0]) as archive:
        project_path, = (name for name in archive.getnames() if name.endswith('/pyproject.toml'))
        with archive.extractfile(project_path) as stream:
            project = tomllib.loads(stream.read().decode())['project']
        assert project['name'] == metadata['Name']
        assert project['version'] == metadata['Version']
        names = {name.split("/", 1)[-1] for name in archive.getnames()}
        assert {"CHANGELOG.md", "docs/releasing.md", "docs/images/uv-map.gif", "docs/validation-manifest.json", "examples/offline.py", "tools/generate_schemas.py",
                "tools/check_distribution.py", "tests/test_schema_helpers.py"} <= names
    with tempfile.TemporaryDirectory(prefix="icon-uv-wheel-") as directory:
        subprocess.run(["uv", "run", "--isolated", "--no-project", "--with", str(wheel),
                        "python", "-c", SMOKE], cwd=directory, check=True)


if __name__ == "__main__":
    main()
