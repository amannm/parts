"""Plugin protocols, registry, and discovery."""

from simstack.plugins.loader import load_plugins
from simstack.plugins.registry import PluginRegistry

__all__ = ["load_plugins", "PluginRegistry"]
