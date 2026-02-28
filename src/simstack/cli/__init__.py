"""Command-line interface for the current SimStack architecture."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from simstack.cache import ArtifactStore
from simstack.domain import load_study_config
from simstack.plugins import load_plugins
from simstack.runner import ExplorationRunner, StudyRunner


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="simstack", description="SimStack pipeline runner")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run a SimStack study")
    run.add_argument("config", help="Path to study YAML")
    run.add_argument("--out", default=None, help="Output directory override")
    run.add_argument("--dry-run", action="store_true", help="Plan and hash DAG without executing compute stages")
    run.add_argument("--force", action="store_true", help="Disable reuse for this run")
    run.add_argument("--resumable", action="store_true", help="Continue DAG execution after node failures")

    validate = sub.add_parser("validate", help="Validate a study config file")
    validate.add_argument("config", help="Path to study YAML")

    sweep = sub.add_parser("sweep", help="Run exploration")
    sweep_sub = sweep.add_subparsers(dest="sweep_command", required=True)

    sweep_run = sweep_sub.add_parser("run", help="Run exploration config")
    sweep_run.add_argument("config", help="Path to study YAML with exploration section")
    sweep_run.add_argument("--dry-run", action="store_true", help="Enumerate exploration runs without executing studies")
    sweep_run.add_argument("--force", action="store_true", help="Disable reuse for exploration runs")

    sweep_opt = sweep_sub.add_parser("optimize", help="Run optimization mode")
    sweep_opt.add_argument("config", help="Path to study YAML with exploration section")
    sweep_opt.add_argument("--dry-run", action="store_true", help="Enumerate optimization trials without executing studies")
    sweep_opt.add_argument("--force", action="store_true", help="Disable reuse for optimization runs")

    parts = sub.add_parser("parts", help="Part catalog commands")
    parts_sub = parts.add_subparsers(dest="parts_command", required=True)
    parts_sub.add_parser("list", help="List catalog parts")

    parts_show = parts_sub.add_parser("show", help="Show part details")
    parts_show.add_argument("name", help="Catalog part name")

    parts_scaffold = parts_sub.add_parser("scaffold-config", help="Scaffold a baseline config for a catalog part")
    parts_scaffold.add_argument("name", help="Catalog part name")
    parts_scaffold.add_argument("--out", required=True, help="Output YAML path")

    cache = sub.add_parser("cache", help="Artifact cache commands")
    cache_sub = cache.add_subparsers(dest="cache_command", required=True)
    cache_sub.add_parser("prune", help="Delete all cached artifacts")

    return parser


def _cmd_run(args: argparse.Namespace) -> int:
    config = load_study_config(args.config)
    if args.out is not None:
        config = config.model_copy(update={"outputs": config.outputs.model_copy(update={"directory": args.out})})
    if args.force:
        config = config.model_copy(update={"outputs": config.outputs.model_copy(update={"reuse": False})})

    runner = StudyRunner(config, repo_root=Path.cwd())
    if args.dry_run:
        result = runner.dry_run()
    else:
        result = runner.run(resumable=bool(args.resumable))
    print(f"Run completed. Output directory: {result.get('out_dir')}")
    if result.get("run_manifest"):
        print(f"Run manifest: {result['run_manifest']}")
    if result.get("cache_hits"):
        print(f"Cache hits: {', '.join(result['cache_hits'])}")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    _ = load_study_config(args.config)
    print("Config OK")
    return 0


def _cmd_sweep(args: argparse.Namespace, *, optimize: bool) -> int:
    summary = ExplorationRunner(args.config, repo_root=Path.cwd()).run(
        optimize=optimize,
        force=bool(args.force),
        dry_run=bool(args.dry_run),
    )
    print(f"Exploration completed. Runs: {summary['count']}")
    print(f"Exploration output root: {summary['output_root']}")
    if summary.get("best"):
        print(f"Best: {json.dumps(summary['best'], sort_keys=True)}")
    if summary.get("report_path"):
        print(f"Exploration report: {summary['report_path']}")
    return 0


def _cmd_parts_list(_: argparse.Namespace) -> int:
    plugins = load_plugins()
    entries = [plugin.descriptor() for plugin in plugins.parts.values()]
    if not entries:
        print("No catalog parts found.")
        return 0

    for entry in sorted(entries, key=lambda item: str(item.get("name", ""))):
        print(
            f"{entry.get('name', '')}\t{entry.get('builder', '')}\t{entry.get('description', '')}"
        )
    return 0


def _cmd_parts_show(args: argparse.Namespace) -> int:
    plugins = load_plugins()
    if args.name not in plugins.parts:
        raise KeyError(f"Unknown part: {args.name}")
    print(yaml.safe_dump(plugins.parts[args.name].descriptor(), sort_keys=False))
    return 0


def _cmd_parts_scaffold(args: argparse.Namespace) -> int:
    from simstack.cad.build import scaffold_part_config

    payload = scaffold_part_config(args.name)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(yaml.safe_dump(payload, sort_keys=False))

    print(f"Scaffolded config: {out_path}")
    return 0


def _cmd_cache_prune(_: argparse.Namespace) -> int:
    store = ArtifactStore(Path.cwd())
    removed = store.prune()
    print(f"Removed cached artifacts: {removed}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else sys.argv[1:])

    if args.command == "run":
        return _cmd_run(args)
    if args.command == "validate":
        return _cmd_validate(args)
    if args.command == "sweep":
        if args.sweep_command == "run":
            return _cmd_sweep(args, optimize=False)
        if args.sweep_command == "optimize":
            return _cmd_sweep(args, optimize=True)
    if args.command == "parts":
        if args.parts_command == "list":
            return _cmd_parts_list(args)
        if args.parts_command == "show":
            return _cmd_parts_show(args)
        if args.parts_command == "scaffold-config":
            return _cmd_parts_scaffold(args)
    if args.command == "cache":
        if args.cache_command == "prune":
            return _cmd_cache_prune(args)

    parser.print_help()
    return 1
