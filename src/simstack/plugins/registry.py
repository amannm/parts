"""Runtime plugin registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable

from simstack.plugins.protocols import (
    CadBuilderPlugin,
    PartPlugin,
    PhysicsPlugin,
    PostprocessorPlugin,
    TagRulePlugin,
)


@dataclass
class PluginRegistry:
    cad_builders: Dict[str, CadBuilderPlugin] = field(default_factory=dict)
    physics: Dict[str, PhysicsPlugin] = field(default_factory=dict)
    tag_rules: Dict[str, TagRulePlugin] = field(default_factory=dict)
    postprocessors: Dict[str, PostprocessorPlugin] = field(default_factory=dict)
    parts: Dict[str, PartPlugin] = field(default_factory=dict)

    def register_cad_builder(self, plugin: CadBuilderPlugin) -> None:
        if plugin.name in self.cad_builders:
            raise ValueError(f"CAD builder plugin already registered: {plugin.name}")
        self.cad_builders[plugin.name] = plugin

    def register_physics(self, plugin: PhysicsPlugin) -> None:
        if plugin.model in self.physics:
            raise ValueError(f"Physics plugin already registered: {plugin.model}")
        self.physics[plugin.model] = plugin

    def register_tag_rule(self, plugin: TagRulePlugin) -> None:
        if plugin.rule_type in self.tag_rules:
            raise ValueError(f"Tag rule plugin already registered: {plugin.rule_type}")
        self.tag_rules[plugin.rule_type] = plugin

    def register_postprocessor(self, plugin: PostprocessorPlugin) -> None:
        if plugin.name in self.postprocessors:
            raise ValueError(f"Postprocessor plugin already registered: {plugin.name}")
        self.postprocessors[plugin.name] = plugin

    def register_part(self, plugin: PartPlugin) -> None:
        if plugin.name in self.parts:
            raise ValueError(f"Part plugin already registered: {plugin.name}")
        self.parts[plugin.name] = plugin

    def plugin_versions(self) -> Dict[str, str | None]:
        versions: Dict[str, str | None] = {}
        for group, names in (
            ("cad", self.cad_builders.keys()),
            ("physics", self.physics.keys()),
            ("tag_rules", self.tag_rules.keys()),
            ("post", self.postprocessors.keys()),
            ("parts", self.parts.keys()),
        ):
            versions[group] = ",".join(sorted(names)) if names else None
        return versions


def iter_plugins(registry: PluginRegistry) -> Iterable[tuple[str, str]]:
    for name in registry.cad_builders:
        yield ("cad", name)
    for name in registry.physics:
        yield ("physics", name)
    for name in registry.tag_rules:
        yield ("tag_rules", name)
    for name in registry.postprocessors:
        yield ("post", name)
    for name in registry.parts:
        yield ("parts", name)
