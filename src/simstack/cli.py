"""Command-line interface for SimStack."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from simstack.cad.build import get_part_catalog_entry, load_part_catalog, scaffold_part_config
from simstack.config import SweepConfig, load_config, load_sweep_config
from simstack.core.project import Project
from simstack.optimize import run_optimize
from simstack.sweep import run_sweep


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="simstack", description="SimStack pipeline runner")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run a SimStack study")
    run.add_argument("config", help="Path to config YAML")
    run.add_argument("--out", default="out", help="Output directory (default: out)")
    run.add_argument("--dry-run", action="store_true", help="Only validate and emit dry-run report")
    run.add_argument("--force", action="store_true", help="Ignore cached outputs and re-run")

    validate = sub.add_parser("validate", help="Validate a config file")
    validate.add_argument("config", help="Path to config YAML")

    sweep = sub.add_parser("sweep", help="Run sweep or optimization")
    sweep_sub = sweep.add_subparsers(dest="sweep_command", required=True)

    sweep_run = sweep_sub.add_parser("run", help="Run a sweep config")
    sweep_run.add_argument("config", help="Path to sweep config YAML")
    sweep_run.add_argument("--out", default=None, help="Sweep output directory root")
    sweep_run.add_argument("--dry-run", action="store_true", help="Only validate and emit dry-run reports")
    sweep_run.add_argument("--force", action="store_true", help="Ignore cached outputs and re-run")

    sweep_opt = sweep_sub.add_parser("optimize", help="Run optimization (alias for mode=optuna)")
    sweep_opt.add_argument("config", help="Path to sweep config YAML")
    sweep_opt.add_argument("--out", default=None, help="Optimization output directory root")
    sweep_opt.add_argument("--dry-run", action="store_true", help="Only validate and emit dry-run reports")
    sweep_opt.add_argument("--force", action="store_true", help="Ignore cached outputs and re-run")

    parts = sub.add_parser("parts", help="Part catalog commands")
    parts_sub = parts.add_subparsers(dest="parts_command", required=True)

    parts_sub.add_parser("list", help="List catalog parts")

    parts_show = parts_sub.add_parser("show", help="Show part details")
    parts_show.add_argument("name", help="Catalog part name")

    parts_scaffold = parts_sub.add_parser("scaffold-config", help="Scaffold a baseline config for a catalog part")
    parts_scaffold.add_argument("name", help="Catalog part name")
    parts_scaffold.add_argument("--out", required=True, help="Output YAML path")

    return parser


def _cmd_run(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    if args.out:
        config = config.model_copy(
            update={
                "outputs": config.outputs.model_copy(update={"directory": args.out}),
            }
        )
    if args.force:
        config = config.model_copy(
            update={
                "outputs": config.outputs.model_copy(update={"reuse": False}),
            }
        )
    project = Project(config, repo_root=Path.cwd())

    out_dir = project.output_root()
    if args.dry_run:
        report_path = project.write_dry_run_report(out_dir / "reports")
        if config.outputs.write_reports:
            project.write_provenance(out_dir / "reports")
        print(f"Dry run completed. Report: {report_path}")
        print(f"Output directory: {out_dir}")
        return 0

    results = project.run()
    print(f"Run completed. Outputs: {results.get('outputs')}")
    if results.get("out_dir"):
        print(f"Output directory: {results['out_dir']}")
    if results.get("provenance"):
        print(f"Provenance: {results['provenance']}")
    if results.get("artifact_index"):
        print(f"Artifact index: {results['artifact_index']}")
    if results.get("paraview_state"):
        print(f"ParaView state template: {results['paraview_state']}")
    if results.get("paraview_macro"):
        print(f"ParaView macro: {results['paraview_macro']}")
    if results.get("stage_hashes"):
        print(f"Stage hashes: {results['stage_hashes']}")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    path = args.config
    try:
        load_config(path)
        print("Config OK")
        return 0
    except Exception as config_exc:
        try:
            load_sweep_config(path)
            print("Sweep config OK")
            return 0
        except Exception:
            raise config_exc


def _run_sweep_command(args: argparse.Namespace, *, optimize: bool) -> int:
    sweep_cfg = load_sweep_config(args.config)
    if optimize:
        summary = run_optimize(
            sweep_cfg,
            repo_root=Path.cwd(),
            dry_run=args.dry_run,
            force=args.force,
            out_dir=args.out,
        )
        print(f"Optimization completed. Trials: {summary['count']}")
        if summary.get("best"):
            print(f"Best: {json.dumps(summary['best'], sort_keys=True)}")
    else:
        summary = run_sweep(
            sweep_cfg,
            repo_root=Path.cwd(),
            dry_run=args.dry_run,
            force=args.force,
            out_dir=args.out,
        )
        print(f"Sweep completed. Runs: {summary['count']}")

    print(f"Sweep output root: {summary['output_root']}")
    if summary.get("report_path"):
        print(f"Sweep report: {summary['report_path']}")
    return 0


def _cmd_parts_list(_: argparse.Namespace) -> int:
    entries = load_part_catalog()
    if not entries:
        print("No catalog parts found.")
        return 0

    for entry in entries:
        name = str(entry.get("name", ""))
        builder = str(entry.get("builder", ""))
        desc = str(entry.get("description", ""))
        print(f"{name}\t{builder}\t{desc}")
    return 0


def _cmd_parts_show(args: argparse.Namespace) -> int:
    entry = get_part_catalog_entry(args.name)
    if entry is None:
        raise KeyError(f"Unknown part: {args.name}")
    print(yaml.safe_dump(entry, sort_keys=False))
    return 0


def _cmd_parts_scaffold(args: argparse.Namespace) -> int:
    payload = scaffold_part_config(args.name)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(yaml.safe_dump(payload, sort_keys=False))
    print(f"Scaffolded config: {out_path}")
    return 0


def _maybe_upgrade_legacy_sweep_argv(argv: list[str]) -> list[str]:
    """Accept legacy `simstack sweep <config>` and map to `sweep run`."""
    if len(argv) >= 2 and argv[0] == "sweep" and argv[1] not in {"run", "optimize", "-h", "--help"}:
        return ["sweep", "run", *argv[1:]]
    return argv


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    argv = list(argv) if argv is not None else sys.argv[1:]
    argv = _maybe_upgrade_legacy_sweep_argv(argv)
    args = parser.parse_args(argv)

    if args.command == "run":
        return _cmd_run(args)
    if args.command == "validate":
        return _cmd_validate(args)
    if args.command == "sweep":
        if args.sweep_command == "run":
            return _run_sweep_command(args, optimize=False)
        if args.sweep_command == "optimize":
            return _run_sweep_command(args, optimize=True)
    if args.command == "parts":
        if args.parts_command == "list":
            return _cmd_parts_list(args)
        if args.parts_command == "show":
            return _cmd_parts_show(args)
        if args.parts_command == "scaffold-config":
            return _cmd_parts_scaffold(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
