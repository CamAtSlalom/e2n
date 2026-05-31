"""Command-line interface for ENEX processing."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import logging
import os
import shutil
import sys
from pathlib import Path

from e2n.enex import ExtractionResult, discover_enex_sources, extract_enex_notes
from e2n.link_resolver import LinkResolutionResult, resolve_evernote_links
from e2n.operation_queue import ResumableOperationQueue
from e2n.notion import (
    NotionBootstrapResult,
    bootstrap_notion_pages,
    ensure_exception_database,
    ensure_import_database,
    NotionClient,
)
from e2n.state import OperationRecord, ProcessingStateStore


LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(prog="e2n", description="Prepare Evernote ENEX exports for Notion migration.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--converting", action="store_true", help="Extract notes from an ENEX file for conversion.")
    mode.add_argument("--reporting", action="store_true", help="Run reporting mode. Not implemented yet.")
    mode.add_argument("--notion-bootstrap", action="store_true", help="Create the Notion migration pages.")
    mode.add_argument("--notion-databases", action="store_true", help="Create or reuse Notion import databases.")
    mode.add_argument("--notion-import", action="store_true", help="Upload extracted notes into Notion databases.")
    mode.add_argument("--resolve-evernote-links", action="store_true", help="Resolve Evernote link placeholders.")
    parser.add_argument("-e", "--enex-source", type=Path, help="Path to a source .enex file or directory of .enex files.")
    parser.add_argument("-d", "--processing-directory", type=Path, help="Directory where processing output is written.")
    parser.add_argument(
        "-w",
        "--workers",
        type=int,
        default=1,
        help="Number of ENEX files to process in parallel when --enex-source is a directory.",
    )
    parser.add_argument("--exceptions-file", type=Path, help="Path to an exceptions.txt file for link resolution.")
    parser.add_argument(
        "-k",
        "--notion-key",
        help="Notion integration key. Can also be supplied with NOTION_KEY or NOTION_TOKEN.",
    )
    parser.add_argument(
        "-n",
        "--notion-root",
        help="Notion root page shared by Evernote Import and Evernote Import Exceptions.",
    )
    parser.add_argument("--resume", action="store_true", help="Resume queued Notion operations for the latest run.")
    parser.add_argument("--reset-run", help="Reset one run id to pending operations before import.")
    parser.add_argument("--wipe-local", help="Delete durable local run state for one run id.")
    parser.add_argument("--wipe-remote", help="Archive mapped Notion pages for one run id and clear mappings.")
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
    if args.workers < 1:
        raise ValueError("--workers must be at least 1")

    results: list[ExtractionResult] = []
    sources = discover_enex_sources(args.enex_source)
    if args.workers == 1 or len(sources) == 1:
        extraction_results = [extract_enex_notes(source, args.processing_directory) for source in sources]
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            extraction_results = list(
                executor.map(lambda source: extract_enex_notes(source, args.processing_directory), sources)
            )

    for result in extraction_results:
        results.append(result)
        print(f"Read {result.total_notes} notes from {result.source}")
        print(f"Wrote processing directory: {result.output_directory}")
        print(f"Successful extractions: {result.success_count}")
        print(f"Extraction errors: {result.error_count}")

    print(f"Processed {len(results)} ENEX file(s)")
    return results


def run_notion_bootstrap(args: argparse.Namespace) -> NotionBootstrapResult:
    """Create or reuse the root child pages used for Notion migration."""
    notion_key = args.notion_key or os.environ.get("NOTION_KEY") or os.environ.get("NOTION_TOKEN")
    if not notion_key:
        raise ValueError("--notion-bootstrap requires -k/--notion-key, NOTION_KEY, or NOTION_TOKEN")

    result = bootstrap_notion_pages(notion_key, root_title=args.notion_root)
    print(f"Using Notion root page: {result.root.title} ({result.root.page_id})")
    print(f"Converted page: {result.converted.title} ({result.converted.page_id})")
    print(f"Exceptions page: {result.exceptions.title} ({result.exceptions.page_id})")
    return result


def run_notion_databases(args: argparse.Namespace) -> None:
    """Create or reuse the import and exception databases."""
    if args.enex_source is None:
        raise ValueError("--notion-databases requires -e/--enex-source")
    notion_key = args.notion_key or os.environ.get("NOTION_KEY") or os.environ.get("NOTION_TOKEN")
    if not notion_key:
        raise ValueError("--notion-databases requires -k/--notion-key, NOTION_KEY, or NOTION_TOKEN")

    bootstrap = bootstrap_notion_pages(notion_key, root_title=args.notion_root)
    notion = NotionClient(notion_key)
    sources = discover_enex_sources(args.enex_source)
    for source in sources:
        database = ensure_import_database(notion, bootstrap.converted.page_id, source.stem)
        print(f"Import database: {database.title} ({database.database_id})")
    exception_database = ensure_exception_database(notion, bootstrap.exceptions.page_id)
    print(f"Exception database: {exception_database.title} ({exception_database.database_id})")


def run_resolve_evernote_links(args: argparse.Namespace) -> list[LinkResolutionResult]:
    """Resolve Evernote embedded link warning placeholders."""
    if args.exceptions_file is None:
        raise ValueError("--resolve-evernote-links requires --exceptions-file")
    notion_key = args.notion_key or os.environ.get("NOTION_KEY") or os.environ.get("NOTION_TOKEN")
    if not notion_key:
        raise ValueError("--resolve-evernote-links requires -k/--notion-key, NOTION_KEY, or NOTION_TOKEN")

    results = resolve_evernote_links(args.exceptions_file, notion_key)
    resolved = sum(1 for result in results if result.updated)
    matched = sum(1 for result in results if result.matched_page is not None)
    print(f"Evernote links scanned: {len(results)}")
    print(f"Matched Notion pages: {matched}")
    print(f"Updated placeholders: {resolved}")
    return results


def run_notion_import(args: argparse.Namespace) -> None:
    """Queue and execute resumable Notion import operations for extracted notes."""
    if args.enex_source is None:
        raise ValueError("--notion-import requires -e/--enex-source")
    if args.processing_directory is None:
        raise ValueError("--notion-import requires -d/--processing-directory")

    notion_key = args.notion_key or os.environ.get("NOTION_KEY") or os.environ.get("NOTION_TOKEN")
    if not notion_key and args.wipe_remote:
        raise ValueError("--wipe-remote requires -k/--notion-key, NOTION_KEY, or NOTION_TOKEN")
    if not notion_key and not args.wipe_local:
        raise ValueError("--notion-import requires -k/--notion-key, NOTION_KEY, or NOTION_TOKEN")

    sources = discover_enex_sources(args.enex_source)
    bootstrap = bootstrap_notion_pages(notion_key, root_title=args.notion_root) if notion_key else None
    notion = NotionClient(notion_key) if notion_key else None

    for source in sources:
        output_directory = args.processing_directory.expanduser().resolve() / source.stem
        state_path = output_directory / "state.db"
        if not state_path.exists():
            raise FileNotFoundError(f"No state.db found for source: {source}. Run --converting first.")

        state = ProcessingStateStore(state_path)
        try:
            run_id = _resolve_run_id(state, args)
            if run_id is None:
                raise ValueError(f"No recorded run in {state_path}. Run --converting first.")

            existing_counts = state.count_operations_by_status(run_id)
            if (
                existing_counts.get("committed", 0) > 0
                and not args.resume
                and not args.reset_run
                and not args.wipe_local
                and not args.wipe_remote
            ):
                raise ValueError(
                    f"Run {run_id} already has committed operations. "
                    "Use --resume to continue, --reset-run to restart, or wipe flags to clean up."
                )

            if args.reset_run:
                reset_count = state.reset_run(run_id)
                print(f"Reset run {run_id}: {reset_count} operation(s) set to pending")

            if args.wipe_remote:
                if notion is None:
                    raise ValueError("--wipe-remote requires a Notion key")
                notion_ids = state.list_notion_object_ids(run_id)
                for notion_object_id in notion_ids:
                    notion.archive_page(notion_object_id)
                removed = state.clear_notion_map(run_id)
                print(f"Wiped remote mappings for run {run_id}: archived {len(notion_ids)} page(s), cleared {removed} mapping(s)")

            if args.wipe_local:
                state.close()
                state = None
                output_path = output_directory
                if output_path.exists():
                    shutil.rmtree(output_path)
                print(f"Wiped local processing output for run {run_id}: {output_path}")
                continue

            if notion is None or bootstrap is None:
                continue

            import_database = ensure_import_database(notion, bootstrap.converted.page_id, source.stem)
            extracted_notes = state.list_notes(run_id, status="extracted")
            for note in extracted_notes:
                idempotency_key = f"{note.note_id}:create_database_row:{note.content_hash}"
                state.enqueue_operation(
                    run_id=run_id,
                    note_id=note.note_id,
                    operation_type="create_database_row",
                    payload={
                        "database_id": import_database.database_id,
                        "title": note.title,
                        "tags": list(note.tags),
                    },
                    idempotency_key=idempotency_key,
                )

            queue = ResumableOperationQueue(state)
            processed = 0
            while True:
                operation = queue.run_once(run_id, handler=lambda op: _execute_notion_operation(notion, op))
                if operation is None:
                    break
                processed += 1

            counts = state.count_operations_by_status(run_id)
            print(
                f"Imported source {source.name}: processed {processed} operation(s), "
                f"committed={counts.get('committed', 0)} failed={counts.get('failed', 0)} "
                f"pending={counts.get('pending', 0)}"
            )
        finally:
            if state is not None:
                state.close()


def _resolve_run_id(state: ProcessingStateStore, args: argparse.Namespace) -> str | None:
    """Resolve the target run id from explicit CLI flags or latest run state."""
    explicit_run_id = args.reset_run or args.wipe_local or args.wipe_remote
    if explicit_run_id:
        if not state.run_exists(explicit_run_id):
            raise ValueError(f"Unknown run id: {explicit_run_id}")
        return explicit_run_id

    latest = state.latest_run_id()
    if latest is None:
        return None
    return latest


def _execute_notion_operation(notion: NotionClient, operation: OperationRecord) -> str:
    """Execute one queued Notion operation and return the resulting object id."""
    payload = operation.payload
    if operation.operation_type == "create_database_row":
        page = notion.create_database_row(
            database_id=str(payload["database_id"]),
            title=str(payload["title"]),
            tags=tuple(str(value) for value in payload.get("tags", [])),
        )
        return page.page_id

    raise ValueError(f"Unsupported operation type: {operation.operation_type}")


def main(argv: list[str] | None = None) -> int:
    """Run the e2n command-line interface."""
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.verbose)

    try:
        if args.reporting:
            raise NotImplementedError("--reporting is accepted but not implemented in this first effort")
        if args.notion_bootstrap:
            run_notion_bootstrap(args)
        elif args.notion_databases:
            run_notion_databases(args)
        elif args.notion_import:
            run_notion_import(args)
        elif args.resolve_evernote_links:
            run_resolve_evernote_links(args)
        else:
            run_converting(args)
    except Exception as exc:
        LOGGER.error("%s", exc)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
