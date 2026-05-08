"""Command-line interface for ENEX processing."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from e2n.enex import ExtractionResult, discover_enex_sources, extract_enex_notes


LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(prog="e2n", description="Prepare Evernote ENEX exports for Notion migration.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--converting", action="store_true", help="Extract notes from an ENEX file for conversion.")
    mode.add_argument("--reporting", action="store_true", help="Run reporting mode. Not implemented yet.")
    parser.add_argument("-e", "--enex-source", type=Path, help="Path to a source .enex file or directory of .enex files.")
    parser.add_argument("-d", "--processing-directory", type=Path, help="Directory where processing output is written.")
    parser.add_argument("-k", "--notion-key", help="Notion integration key. Accepted for future Notion upload support.")
    parser.add_argument(
        "-n",
        "--notion-root",
        help="Notion root page shared by enex-converted and enex-exceptions. Accepted for future support.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging.")
    return parser


def configure_logging(verbose: bool) -> None:
    """Configure process logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(message)s")


def run_converting(args: argparse.Namespace) -> list[ExtractionResult]:
    """Run ENEX extraction for conversion preparation."""
    if args.enex_source is None:
        raise ValueError("--converting requires -e/--enex-source")
    if args.processing_directory is None:
        raise ValueError("--converting requires -d/--processing-directory")

    results: list[ExtractionResult] = []
    sources = discover_enex_sources(args.enex_source)
    for source in sources:
        result = extract_enex_notes(source, args.processing_directory)
        results.append(result)
        print(f"Read {result.total_notes} notes from {result.source}")
        print(f"Wrote processing directory: {result.output_directory}")
        print(f"Successful extractions: {result.success_count}")
        print(f"Extraction errors: {result.error_count}")

    print(f"Processed {len(results)} ENEX file(s)")
    return results


def main(argv: list[str] | None = None) -> int:
    """Run the e2n command-line interface."""
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.verbose)

    try:
        if args.reporting:
            raise NotImplementedError("--reporting is accepted but not implemented in this first effort")
        run_converting(args)
    except Exception as exc:
        LOGGER.error("%s", exc)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
