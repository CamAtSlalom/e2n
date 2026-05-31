# User Instructions

## Purpose

This first version prepares Evernote export files for later Notion conversion. It reads one `.enex` file, or every `.enex` file in a source directory, extracts each note into its own file, and creates tracking files in a processing directory.

Evernote export files are expected under:

```text
~/Downloads/Imports/Notebooks
```

## Supported operating systems

The tool is intended to run on macOS, Ubuntu, and WSL. Use normal paths for your operating system. `~` is supported for your home directory.

## Command

```bash
e2n --converting -e ~/Downloads/Imports/Notebooks/Enduring.enex -d ./processing
```

When running from a source checkout before installing the package:

```bash
PYTHONPATH=src python -m e2n.cli --converting -e ~/Downloads/Imports/Notebooks/Enduring.enex -d ./processing
```

To run the local web interface:

```bash
e2n-ui --open
```

If command shims are not refreshed yet, run:

```bash
PYTHONPATH=src python -m e2n.webui.server --open
```

By default, it listens on `http://127.0.0.1:8787`.

## Parameters

`--converting`

Extract records from the `.enex` file. This is the only working mode in the first version.

`--reporting`

Accepted by the command line, but not implemented yet.

`--resolve-evernote-links`

Post-import resolver for embedded Evernote links. It reads `exceptions.txt`,
uses each `Evernote Link` row's visible link text to search for an identically
named Notion page/database row, and updates the warning placeholder block when a
single exact match is found.

`--notion-databases`

Creates or reuses the Notion databases needed for import. Each `.enex` source
gets one database named after the `.enex` file stem inside `Evernote Import`.
The exception database is named `Import-Exceptions` inside
`Evernote Import Exceptions`.

`--notion-import`

Imports extracted notes into each source database under `Evernote Import` using
durable local queue state in `state.db`. Operations are rate-limited to respect
Notion limits and can be resumed safely.

`-e`, `--enex-source`

The `.enex` file to read, or a directory containing `.enex` files. When a directory is provided, every direct child `*.enex` file is processed in sorted order.

Example:

```text
~/Downloads/Imports/Notebooks/Enduring.enex
```

`-d`, `--processing-directory`

The parent directory for processing output. The tool creates a child directory named after the `.enex` file.

Example:

```text
./processing
```

With `Enduring.enex`, the output directory becomes:

```text
./processing/Enduring
```

The same destination tree will later hold extracted resources from the notes, such as files that need to be uploaded or manually inserted into Notion.

`-w`, `--workers`

Number of `.enex` files to process in parallel when `--enex-source` points at a
directory. Use `1` for deterministic single-file-at-a-time processing.

`--exceptions-file`

Path to an `exceptions.txt` file used by `--resolve-evernote-links`.

`-k`, `--notion-key`

The Notion integration key. Required for Notion API modes, including
`--notion-bootstrap`, `--notion-databases`, `--notion-import`, and
`--wipe-remote`.

`-n`, `--notion-root`

The Notion parent page where `Evernote Import` and `Evernote Import Exceptions` will be managed. If omitted, the tool creates or reuses those pages as top-level workspace pages when the integration type allows it.

`--resume`

Continue processing a run that already has committed operations.

`--reset-run`

Run id to reset back to pending operations before import retry.

`--wipe-local`

Run id whose local processing directory should be removed.

`--wipe-remote`

Run id whose mapped Notion pages should be archived and removed from local
mapping state.

## Output files

For `Enduring.enex`, the output structure is:

```text
processing/
  Enduring/
    notes/
      note_000001.enex
      note_000002.enex
    state.db
    master.txt
    success.txt
    errors.txt
```

`master.txt`

One line per extracted note. Each line contains the generated note id, note title, extracted note file path, comma-separated Evernote tags, and comma-separated exception reasons.

`success.txt`

One line per note that was successfully extracted.

`errors.txt`

One line per note that failed extraction. An empty file means there were no extraction errors.

`exceptions.txt`

One line per successfully extracted note that already needs a future exception database row. Empty titles are normalized to `Empty Title` and recorded with the `Empty Title` reason. Notes with no content and no resources are recorded with the `No Content` reason. Embedded `evernote://` links are recorded with the `Evernote Link` reason, the visible link text, and the original link value. If multiple note-level reasons apply, all reasons are preserved.

Later conversion may add `Unsupported Content` exception rows for notes that do
contain data but include content that cannot be imported into supported Notion
blocks. This is not treated as `No Content`.

Embedded links, resources, and documents may appear inside existing text. During
conversion planning, the text is split above and below each non-text item so the
non-text item can become its own Notion block. Large text blocks are split into
smaller chunks before import to stay within Notion block-size limits.

Future exception reporting will include links or durable references to extracted resources that could not be inserted automatically, so they can be manually placed into the correct imported Notion note.

`state.db`

Durable local run state in SQLite. This file tracks extraction runs, note-level
status, and resumable operation metadata for restart-safe imports and
incremental testing.

## Count

Every converting run prints the number of notes read from the `.enex` file, the output directory, the number of successful extractions, and the number of extraction errors.
