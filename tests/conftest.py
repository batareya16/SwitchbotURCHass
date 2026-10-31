"""Load integration and add-on modules without importing Home Assistant.

Both packages pull in Home Assistant and bluezero at import time, which a test run has no
business needing. Everything tested here is deliberately free of those dependencies, so the
modules are loaded straight from their files, under stand-in packages whose `__path__` lets
their relative imports resolve without running the real `__init__`.
"""
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "switchbot_urc"
ADDON = ROOT / "addons" / "switchbot_urc_bridge"

_PACKAGES = {INTEGRATION: "switchbot_urc", ADDON: "urc_addon"}


def _package_for(path: Path) -> str:
    name = _PACKAGES[path.parent]
    if name not in sys.modules:
        package = types.ModuleType(name)
        package.__path__ = [str(path.parent)]
        sys.modules[name] = package
    return name


def load(path: Path, name: str | None = None):
    """Import one module by file path, as a submodule of its stand-in package."""
    package = _package_for(path)
    full_name = f"{package}.{path.stem}"
    if full_name in sys.modules:
        return sys.modules[full_name]
    spec = importlib.util.spec_from_file_location(full_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    if name:
        sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
