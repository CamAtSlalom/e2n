# enex2notion2026

First-pass Evernote `.enex` preparation tool for a later Notion migration.

See [docs/users.md](docs/users.md) for user instructions and parameter explanations.

## Local web interface

The project includes a local-first web interface intended for self-serve usage.
It runs fully on your machine and uses your existing local processing
directories.

Start the interface:

```bash
e2n-ui --open
```

If your shell has not refreshed new script shims yet, use:

```bash
PYTHONPATH=src python -m e2n.webui.server --open
```

Default URL:

```text
http://127.0.0.1:8787
```

Common options:

```bash
e2n-ui --host 127.0.0.1 --port 8787 --open
e2n-ui --reload
```

Security default: the server binds to `127.0.0.1` unless you explicitly set a
different host.

The UI provides:

- Extraction runs
- Notion import queue execution
- Run controls (`reset`, `wipe-local`, `wipe-remote`)
- Local dashboard cards from `state.db`

## Support

If this tool saves you time and you want to contribute a coffee, you can use
[Buy Me a Coffee](https://www.buymeacoffee.com/CamBeeler) or the digital coin
wallets listed in [CameronBeeler/donation-wallets](https://github.com/CameronBeeler/donation-wallets).

## Supported operating systems

This project is written in Python and uses `pathlib` for paths, so the same commands work on macOS, Ubuntu, and WSL. Shell examples use POSIX-style paths because the expected Evernote exports are in:

```text
~/Downloads/Imports/Notebooks
```

## Parameters

`--converting`

Runs conversion preparation. In this first effort, it reads one `.enex` export file, extracts each `<note>` record, and writes processing files.

`--reporting`

Reserved for report-only runs. It is accepted by the command line but is not implemented in this first effort.

`--notion-bootstrap`

Creates the Notion migration pages. If `--notion-root` is provided, the
integration must have access to a Notion page with that exact title, and the
migration pages are created under it. If no root is provided, the tool creates
or reuses top-level workspace pages.

`--notion-databases`

Creates or reuses the Notion databases needed for import. Each `.enex` source
gets one database named after the `.enex` file stem inside `Evernote Import`.
The exception database is named `Import-Exceptions` inside
`Evernote Import Exceptions`.

`--notion-import`

Imports extracted notes into each source import database using queue state in
`state.db`. Operations are durable and restart-safe.

`--resolve-evernote-links`

Post-import resolver for embedded Evernote links. It reads `exceptions.txt`,
uses each `Evernote Link` row's link text to find an identically named Notion
page, and replaces the warning placeholder block with an inline link when a
single exact match is found.

`-e`, `--enex-source`

Path to the Evernote export file. Example:

```text
~/Downloads/Imports/Notebooks/Enduring.enex
```

`-d`, `--processing-directory`

Directory where processing output is created. The tool creates a child directory named after the `.enex` file. For `Enduring.enex`, output goes in:

```text
<processing-directory>/Enduring
```

`-w`, `--workers`

Number of `.enex` files to process in parallel when `--enex-source` points at a
directory. The default is `1`.

`--exceptions-file`

Path to an `exceptions.txt` file used by `--resolve-evernote-links`.

`-k`, `--notion-key`

Notion integration key. Required for Notion API modes (including
`--notion-bootstrap`, `--notion-databases`, `--notion-import`, and
`--wipe-remote`) unless `NOTION_KEY` or `NOTION_TOKEN` is set in the
environment.

`-n`, `--notion-root`

Notion root page for `Evernote Import` and `Evernote Import Exceptions`.

`--resume`

Resume a run that already has committed operations.

`--reset-run`

Reset one run id back to pending operations.

`--wipe-local`

Delete local processing output for one run id.

`--wipe-remote`

Archive mapped Notion pages for one run id and clear local mappings.

## First-pass output

For this command:

```bash
e2n --converting -e ~/Downloads/Imports/Notebooks/Enduring.enex -d ./processing
```

The tool creates:

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
    exceptions.txt
```

`master.txt` contains one line per note with the note id, title, extracted note file path, tags, and exception reasons. `success.txt` records notes extracted successfully. `errors.txt` records notes that could not be extracted. `exceptions.txt` seeds future exception database rows for notes such as `Empty Title`, `No Content`, and `Evernote Link`.

`state.db` stores durable local run and note state in SQLite for restart-safe
execution and resumable import operations.

Empty or whitespace-only note titles are imported as `Empty Title`. Evernote tags are preserved for the future Notion `Tags` multi-select property.

Embedded `evernote://` links are recorded separately because they cannot be
resolved until the entire collection has been imported. Each link keeps its
visible link text and original Evernote link value for later manual confirmation.

During conversion, non-text content embedded inside a text block is split into
separate planned blocks. Text above and below embedded links, resources, and
documents remains in separate text segments. Large text segments are also split
into smaller chunks before Notion block creation.

The command prints the total note count read from the `.enex` file.

`-e` can also point at a directory. In that case, every direct child `*.enex` file is processed in sorted order, with one child output directory per source file.

## Notion bootstrap

To create or reuse the migration pages:

```bash
NOTION_KEY="secret_from_notion" e2n --notion-bootstrap -n "Migration Root"
```

This creates these child pages under the root:

```text
Migration Root/
  Evernote Import/
  Evernote Import Exceptions/
```

The exception page will contain the internal exception tracking database named
`Import-Exceptions`.

## Notion databases

To create or reuse the databases:

```bash
NOTION_KEY="secret_from_notion" e2n --notion-databases -n "ENEX-IMPORT" -e ~/Downloads/Imports/Notebooks
```

Database creation is idempotent. On restart, the tool searches for an exact
database name under the expected parent page and reuses it. It does not create a
second database of the same name under the same parent.

## Evernote link resolver

After all notes are imported and warning placeholder blocks have Notion block
links in `exceptions.txt`, run:

```bash
NOTION_KEY="secret_from_notion" e2n --resolve-evernote-links --exceptions-file ./processing/Enduring/exceptions.txt
```

Rows without a single exact Notion title match are left for manual review. The
original Evernote link value remains in the linkable-text field.
