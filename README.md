# enex2notion2026

First-pass Evernote `.enex` preparation tool for a later Notion migration.

See [docs/users.md](docs/users.md) for user instructions and parameter explanations.

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

`-k`, `--notion-key`

Notion integration key. Accepted now so scripts can use the final parameter shape, but it is not used until Notion upload code is added.

`-n`, `--notion-root`

Notion root page for `enex-converted` and `enex-exceptions`. Accepted now so scripts can use the final parameter shape, but it is not used until Notion upload code is added.

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
    master.txt
    success.txt
    errors.txt
```

`master.txt` contains one line per note with the note id, title, and extracted note file path. `success.txt` records notes extracted successfully. `errors.txt` records notes that could not be extracted.

The command prints the total note count read from the `.enex` file.

`-e` can also point at a directory. In that case, every direct child `*.enex` file is processed in sorted order, with one child output directory per source file.
