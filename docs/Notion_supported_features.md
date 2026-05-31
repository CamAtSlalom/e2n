# Notion Supported Features (SDK + Public API)

Generated: 2026-05-31
Posted: 2026-05-31
Review cadence: Revalidate quarterly or on Notion API version change.

## Scope and Method

This inventory is based on:

1. Runtime inspection of the installed Python `notion-client` SDK in this environment.
2. Programmatic parsing of Notion's published OpenAPI specification.
3. Spot-checking current Notion public API reference pages (API version shown in docs: `2026-03-11`).

This is a practical capability inventory for migration planning, backed by the full published API operation map.

## OpenAPI Coverage Snapshot

- OpenAPI operations parsed: 47
- Endpoint groups discovered:
  - `Views`: 8
  - `Pages`: 7
  - `Blocks`: 5
  - `Data sources`: 5
  - `Comments`: 5
  - `File uploads`: 5
  - `Users`: 3
  - `Databases`: 3
  - `OAuth`: 3
  - `Search`: 1
  - `Custom emojis`: 1
  - `Meeting notes`: 1

## Public SDK Surface Observed (Python notion-client)

### Top-level client methods

- `search`
- `request`
- `close`

### Resource groups and methods

- `blocks`
  - methods: `retrieve`, `update`, `delete`
  - subresource: `children.append`, `children.list`
- `databases`
  - methods: `create`, `retrieve`, `update`
- `data_sources`
  - methods: `create`, `retrieve`, `update`, `query`, `list_templates`
- `pages`
  - methods: `create`, `retrieve`, `update`, `move`, `retrieve_markdown`, `update_markdown`
  - subresource: `properties.retrieve`
- `users`
  - methods: `list`, `retrieve`, `me`
- `comments`
  - methods: `create`, `retrieve`, `update`, `delete`, `list`
- `file_uploads`
  - methods: `create`, `send`, `complete`, `retrieve`, `list`
- `oauth`
  - methods: `token`, `introspect`, `revoke`

## Notion API Feature Areas Relevant to e2n

### Strongly supported by Notion API

- Workspace/page search.
- Page creation and update.
- Data source (database-like) creation/query/update.
- Block tree operations (read children, append children, update blocks).
- Rich text annotations and links.
- File upload lifecycle via File Upload object APIs.
- Comments APIs.

### Block/content types shown in API reference responses

Notion block responses include (among others): paragraph, headings, bulleted/numbered list item, quote, to_do, toggle, code, callout, divider, table, table_row, embed, bookmark, image, video, pdf, file, audio, link_preview, unsupported.

## What This Means for e2n

### Available to implement now

- Per-ENEX-file import containers using data sources/databases.
- Rich text + inline URL links.
- Child block append/update workflows.
- Warning callouts for unsupported/deferred items.
- Upload-first attachment flow using `file_uploads` lifecycle.

### Important nuance: "Notion supports" vs "current e2n supports"

- Notion API supports many object families that current e2n code does not yet map end-to-end.
- Current e2n Phase 1 implementation intentionally narrows support and routes unknown/unsupported content to exception callouts.

## Notion API Limits / Behavioral Constraints to Respect

- Cursor pagination on list/query/search endpoints.
- Request and rate limits (handle 429 with retry/backoff).
- Capability-scoped access (content read/write permissions gate endpoints).
- String/property nullability rules (Notion does not accept empty strings in some contexts).

## Migration-Oriented Support Matrix (Notion API vs Current e2n)

| Capability | Notion API support | Current e2n status |
| --- | --- | --- |
| Create/update pages | Yes | Yes |
| Create/reuse import databases/data sources | Yes | Yes |
| Add paragraph/text blocks | Yes | Yes |
| Inline HTTP/HTTPS links in text | Yes | Yes (Phase 1) |
| Evernote internal note links | No direct concept; can represent links/mentions | Deferred with warning callout + exception |
| Images | Yes | Yes (when resource URL is available) |
| PDFs | Yes | Yes (when resource URL is available) |
| Generic files | Yes | Partial (mapped, depends on upload/link flow) |
| Audio/video attachments | Yes in block model, upload/attachment constraints apply | Currently treated as unsupported for safe import |
| ENML tables | Yes as Notion table blocks (API has table/table_row) | Currently treated as unsupported placeholder |
| Comments | Yes | Not used yet |
| File upload APIs (`create/send/complete`) | Yes | Not wired end-to-end yet |

## Recommended Next Steps

1. Implement file-upload pipeline (`file_uploads.create -> send -> complete`) and attach uploaded files to target blocks.
2. Add explicit table conversion strategy (ENML table -> Notion table/table_row) with fallback callout on edge cases.
3. Add capability flags in config so users can choose strict mode (only proven mappings) vs experimental mode (broader mappings).
4. Keep this file versioned as Notion API revisions land.

## Aging Notice

This document can age quickly when Notion publishes new API versions or SDK updates.
Any migration decisions should be based on the latest API version notes plus a
fresh SDK/OpenAPI inventory run.
