# Notion Attribute Gaps

This project treats unsupported Evernote-to-Notion attribute mappings as planned
manual-recovery work, not silent loss.

## Contract

When an Evernote note attribute cannot be represented through the current Notion
SDK/API:

1. Record the gap in this document as a future feature objective.
2. Preserve the original source value in the processing directory when feasible.
3. Add a visible marker block on the Notion page or database row where the
   attribute belongs.
4. Add an exception database row under `Evernote Import Exceptions`.
5. Link the exception row to the marker block, not only to the page.
6. Include a clear manual correction message.
7. Include any external resource path or durable reference needed to complete
   the manual correction.

The imported note still counts as handled only after both the marker block and
the exception row are created.

Unsupported content is distinct from empty content. If a note contains data but
part of that data cannot be converted into supported Notion blocks, add a
visible error/comment block to the imported Notion page or row and create an
exception database row with `Reason = Unsupported Content`.

Embedded Evernote links are also handled as manual-recovery work. During import,
retain each link name in its own warning callout block, create an exception row
with `Reason = Evernote Link`, link the exception row to that block, and store
the original `evernote://` value in the row's linkable-text field.

## Exception Row Requirements

Each unsupported-attribute exception should include:

- Note name
- Source `.enex` file
- Reason multi-select values
- Evernote attribute name
- Intended Notion page/database property or block target
- Link to the marker block on the imported page
- Manual correction message
- Documentation gap summary
- Future feature objective
- External resource path or durable reference, when applicable

## Initial Gap Inventory

This inventory should be filled as conversion work identifies concrete gaps.

| Evernote attribute | Intended Notion target | Current gap | Manual recovery |
| --- | --- | --- | --- |
| TBD | TBD | TBD | TBD |
