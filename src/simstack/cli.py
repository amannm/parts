"""Command-line interface for SimStack."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from simstack.config import load_config
from simstack.core.project import Project


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="simstack", description="SimStack pipeline runner")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run a SimStack study")
    run.add_argument("config", help="Path to config YAML")
    run.add_argument("--out", default="out", help="Output directory (default: out)")
    run.add_argument("--dry-run", action="store_true", help="Only validate and emit dry-run report")

    validate = sub.add_parser("validate", help="Validate a config file")
    validate.add_argument("config", help="Path to config YAML")

    return parser


def _cmd_run(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    if args.out:
        config = config.model_copy(
            update={
                "outputs": config.outputs.model_copy(update={"directory": args.out}),
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
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    load_config(args.config)
    print("Config OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        return _cmd_run(args)
    if args.command == "validate":
        return _cmd_validate(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
