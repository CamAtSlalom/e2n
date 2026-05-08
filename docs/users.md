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

## Parameters

`--converting`

Extract records from the `.enex` file. This is the only working mode in the first version.

`--reporting`

Accepted by the command line, but not implemented yet.

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

`-k`, `--notion-key`

The Notion integration key. This parameter is accepted now but is not used until Notion upload is added.

`-n`, `--notion-root`

The Notion root page where `enex-converted` and `enex-exceptions` will be managed. This parameter is accepted now but is not used until Notion upload is added.

## Output files

For `Enduring.enex`, the output structure is:

```text
processing/
  Enduring/
    notes/
      note_000001.enex
      note_000002.enex
    master.txt
    success.txt
    errors.txt
```

`master.txt`

One line per extracted note. Each line contains the generated note id, note title, and extracted note file path.

`success.txt`

One line per note that was successfully extracted.

`errors.txt`

One line per note that failed extraction. An empty file means there were no extraction errors.

Future exception reporting will include links or durable references to extracted resources that could not be inserted automatically, so they can be manually placed into the correct imported Notion note.

## Count

Every converting run prints the number of notes read from the `.enex` file, the output directory, the number of successful extractions, and the number of extraction errors.
