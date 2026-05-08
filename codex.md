# enex2notion2026

Evernote `.enex` to Notion migration tool. Converts Evernote notebooks into Notion pages, databases, and blocks via the Notion API.

- **Author**: CameronBeeler (cameron.beeler@icloud.com)
- **Version**: 1.0.0
- **Homepage**: https://github.com/CameronBeeler/enex2notion
- **License**: Apache 2.0 — this is an original work by CameronBeeler. All contributors must be credited. This project was not derived from or extended from any existing codebase. Never copy code from enex2notion or any other repository.

## Language & Tooling

- **Python** is the only language for this project.
- Line length: 120 (black and ruff).
- Use `lxml` for ENEX/XML parsing, `beautifulsoup4` for ENML-to-blocks conversion, `notion-client` (official Python SDK) for all Notion API calls.
- Add additional libraries for data manipulation as needed (e.g., `pandas`, `hashlib`, `base64`).
- Async (`AsyncClient`) is preferred for Notion API interactions to enable parallel uploads.

## Platform Support

- macOS, Ubuntu, and WSL are all first-class deployment targets.
- Keep platform-specific functions separated (e.g., path handling, process signals) so each platform can be maintained independently.

## Design Imperatives

- Optimize first for correctness, then for efficient memory use, disk I/O, and Notion API throughput.
- Treat every operation as repeatable and externally configured. Do not retain tenant, notebook, source, Notion, or run context in process globals or hidden application state.
- Keep single-file and once-off workflows as thin entry points over reusable services. The same services must support one `.enex` file, every `.enex` file in a source directory, restart runs, and future scheduling.
- Process multiple `.enex` files in deterministic sequence unless an explicit concurrency strategy is introduced. Future concurrency must isolate run context per notebook/file so multi-threaded or multi-tenant execution cannot share mutable state accidentally.
- Use streaming parsers and incremental checkpoint writes for large exports. Avoid designs that require loading full notebooks, all note bodies, or all resources into memory.
- Use the processing directory as the durable handoff location for extracted notes, resources, checkpoints, reports, and retry state.
- Extracted resources from ENEX notes will be materialized under the same destination tree and later uploaded or linked into Notion pages/database rows.
- Exception records must preserve manual recovery paths. When a resource cannot be inserted automatically, the exception database should include a download link or durable local/exported resource reference so the item can be manually inserted into the correct imported note.

## Notion Structure

### enex-converted Page

All successfully converted ENEX notes land under a top-level Notion page named **"enex-converted"**.

- Each `.enex` file produces a **Notion database** inside "enex-converted", named after the source file. For example, importing `Enduring.enex` creates a database called **"Enduring"**.
- Every ENEX note becomes a **row** in its corresponding database.
- Note content is added as **child blocks** of the database row (page), mapping ENML elements to Notion block types (paragraph, heading, to_do, image, pdf, etc.).
- Binary resources (PDFs, images) are decoded from base64, uploaded via the Notion File Upload API, and attached as the appropriate block type.

### Exception Tracking

- A top-level Notion page named **"enex-exceptions"** contains a single **exception tracking database**.
- If a note cannot be fully converted to its matched Notion format, a **basic Notion page** is still created (title + raw text fallback) so that no note is ever lost.
- The failed note is also recorded as a row in the exception tracking database with these properties:
  - **Note Name** (title)
  - **Link** (url — link to the basic fallback page that was created)
  - **Error Message** (rich_text — the exception or conversion failure reason)
  - **Source File** (rich_text — the `.enex` filename it came from)

### Zero-Loss Guarantee

**No note left behind.** Every single ENEX note must be accounted for — either as a fully converted database row or as a fallback row with an exception record. There are no silent drops.

## Checkpoint / Restart

The application supports cancellation and resumption at the individual-note level using file-based tracking in a dedicated processing directory.

### Processing Directory

Named using the pattern: `<enex-notebook-name><timestamp>_processing/`

Contains three tracking files:

- **Master.txt** — On startup, every note identifier from the `.enex` file is written here. This is the source of truth for the full scope of work.
- **Completed.txt** — After a note is successfully converted and confirmed in Notion, its entry is moved from Master.txt to Completed.txt.
- **Errored.txt** — After a note fails conversion (and the fallback + exception record are written), its entry is moved from Master.txt to Errored.txt.

### Failed Execution Directory

If the application terminates abnormally (crash, kill signal, etc.), the processing directory is renamed to: `<enex-notebook-name><timestamp>_failed/`

### Restart Behavior

On restart, the tool detects an existing processing directory (or `_failed` directory) and resumes from where it left off. Notes already in Completed.txt or Errored.txt are skipped. Only notes still in Master.txt are processed.

### Graceful Cancellation

The application must handle SIGINT/SIGTERM (Ctrl+C) gracefully:
1. Finish processing the current note (do not leave a half-written Notion page).
2. Flush tracking files to disk.
3. Exit cleanly so the processing directory is valid for restart.

## Code Style & Conventions

- All code is original. Never reference, copy, or derive from enex2notion or any other existing repository.
- Use type hints throughout.
- Docstrings on all public functions and classes.
- Logging via Python `logging` module — structured, leveled (DEBUG/INFO/WARNING/ERROR).
- Configuration via environment variables and/or a `.env` file (for Notion API token, parent page IDs, etc.).
- Tests use `pytest`. Test discovery and execution must work cross-platform.
