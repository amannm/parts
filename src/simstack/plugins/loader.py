"""Plugin discovery from Python entry points."""

from __future__ import annotations

from importlib import metadata
from typing import Any, Iterable

from simstack.plugins.builtins import register_builtin_plugins
from simstack.plugins.registry import PluginRegistry

ENTRYPOINT_GROUPS = {
    "cad": "simstack.cad_builders",
    "physics": "simstack.physics",
    "tag_rules": "simstack.tag_rules",
    "post": "simstack.postprocessors",
    "parts": "simstack.parts",
}


def _entry_points(group: str) -> Iterable[metadata.EntryPoint]:
    all_eps = metadata.entry_points()
    if hasattr(all_eps, "select"):
        return list(all_eps.select(group=group))
    return list(all_eps.get(group, []))


def _load_entrypoint_plugin(plugin: Any, registry: PluginRegistry, kind: str) -> None:
    if not callable(plugin):
        return

    if kind == "cad":
        registry.register_cad_builder(plugin)
        return
    if kind == "physics":
        registry.register_physics(plugin)
        return
    if kind == "tag_rules":
        registry.register_tag_rule(plugin)
        return
    if kind == "post":
        registry.register_postprocessor(plugin)
        return
    if kind == "parts":
        registry.register_part(plugin)
        return


def load_plugins() -> PluginRegistry:
    registry = PluginRegistry()
    register_builtin_plugins(registry)

    for kind, group in ENTRYPOINT_GROUPS.items():
        for ep in _entry_points(group):
            plugin = ep.load()
            if callable(plugin):
                try:
                    # Factory form: plugin(registry)
                    plugin(registry)
                    continue
                except TypeError:
                    pass
            _load_entrypoint_plugin(plugin, registry, kind)

    return registry
