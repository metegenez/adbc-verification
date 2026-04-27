# NOTE: This module is used at build time to discover host .so paths for
# copying into docker/drivers/. At runtime, driver paths are fixed constants
# in conftest.py.

"""Parse dbc TOML manifests to resolve ADBC driver .so paths."""

from __future__ import annotations

import pathlib
import platform
import tomllib

_MANIFEST_DIR = pathlib.Path.home() / ".config" / "adbc" / "drivers"

# Map platform.machine() values to the dbc manifest arch key suffix.
_ARCH_MAP: dict[str, str] = {
    "x86_64": "amd64",
    "aarch64": "arm64",
    "arm64": "arm64",
}

_ALL_DRIVER_NAMES = ("sqlite", "flightsql", "postgresql", "duckdb")


def _arch_key() -> str:
    """Return the dbc manifest key for the current platform, e.g. 'linux_amd64'."""
    machine = platform.machine()
    suffix = _ARCH_MAP.get(machine)
    if suffix is None:
        raise RuntimeError(
            f"Unsupported architecture '{machine}'; "
            f"expected one of {sorted(_ARCH_MAP)}"
        )
    return f"linux_{suffix}"


def get_driver_path(driver_name: str) -> str:
    """Read driver .so path from a dbc TOML manifest.

    Looks up ``~/.config/adbc/drivers/{driver_name}.toml`` and returns the
    absolute path string under ``[Driver.shared]`` for the current platform.

    Raises ``FileNotFoundError`` if the manifest does not exist (driver not
    installed via ``dbc install {driver_name}``).
    """
    toml_file = _MANIFEST_DIR / f"{driver_name}.toml"
    if not toml_file.exists():
        raise FileNotFoundError(
            f"ADBC driver manifest not found: {toml_file}\n"
            f"Install the driver with: dbc install {driver_name}"
        )
    with open(toml_file, "rb") as fh:
        manifest = tomllib.load(fh)
    arch = _arch_key()
    try:
        so_path = manifest["Driver"]["shared"][arch]
    except KeyError:
        raise FileNotFoundError(
            f"No shared library for arch '{arch}' in {toml_file}; "
            f"available keys: {list(manifest.get('Driver', {}).get('shared', {}))}"
        )
    return so_path


def get_all_driver_paths() -> dict[str, str]:
    """Return ``{name: /path/to/driver.so}`` for all four expected drivers."""
    return {name: get_driver_path(name) for name in _ALL_DRIVER_NAMES}
