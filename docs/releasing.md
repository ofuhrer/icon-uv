# Releasing icon-uv

The package builds a pure-Python wheel and source archive with setuptools and
`uv build`. The wheel includes the radiation table, all JSON schemas and the
license. Its dependencies may install native libraries. Tests and builds run on
Linux with Python 3.11 and 3.13; they do not need forecast-service credentials.

## Prepare a GitHub release

1. Set the same version in `pyproject.toml` and `icon_uv/__init__.py`, update
   `CHANGELOG.md` and the README release-install link, then run `uv lock`.
2. Use a fresh output directory and run the release checks:

   ```sh
   uv sync --locked --extra cams
   uv run --no-sync pytest -q
   uv run --no-sync python tools/generate_schemas.py --check
   uv build --out-dir work/release/0.1.0
   uv run --no-sync python tools/check_distribution.py work/release/0.1.0 --tag v0.1.0
   uv run --no-sync twine check --strict work/release/0.1.0/*
   ```

3. Commit and push the changes. Wait for **Tests and distributions** to pass for
   that commit, then create an annotated `vVERSION` tag on it and push the tag.
4. Download the tested `distributions` artifact from that commit's CI run. Attach
   its wheel and source archive, plus a SHA-256 checksum file, to a GitHub release
   using that tag. Use the changelog entry as the release notes.

The distribution checker verifies resources, matching wheel/source versions,
the release tag and the installed `__version__`. It installs the wheel outside
the source tree and exercises its schemas and radiation table. Twine checks the
package metadata and README. README links are absolute so they also work on PyPI.

## One-time PyPI setup

Sign in to the PyPI account that will own the package and add a
[pending Trusted Publisher](https://pypi.org/manage/account/publishing/):

| Field | Value |
|---|---|
| PyPI project name | `icon-uv` |
| GitHub owner | `ofuhrer` |
| GitHub repository | `icon-uv` |
| Workflow filename | `publish.yml` |
| Environment name | `pypi` |

For an existing project, add the same publisher under its Publishing settings.
The repository's `pypi` GitHub environment should allow deployment from `v*`
tags. The account-side registration must be done on PyPI; adding this workflow
alone does not register the publisher or publish the package.

PyPI creates the project on the first successful publish. A pending publisher
does not reserve the name. See the official [first-project setup guide](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).

## Publish a tested release to PyPI

After the GitHub release exists and the publisher is configured:

```sh
gh workflow run publish.yml --ref v0.1.0
```

**Publish to PyPI** is manual. It rejects branch refs and draft or missing
releases, reruns the CI checks at the selected tag, and publishes the tested
wheel and source archive. Only the publishing job receives `id-token: write`;
building and testing happen in separate jobs. No stored PyPI API token is needed.
The official PyPA action uses [Trusted Publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/)
and generates provenance attestations by default.

Once publication succeeds, users can install with:

```sh
pip install 'icon-uv[cams]==0.1.0'
icon-uv --help
```

Verify installation in a clean environment before announcing the PyPI release.
PyPI versions cannot be overwritten: fix a released package with a new version.
