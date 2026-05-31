# Evernote ENEX Metadata Types and Gap Analysis

Generated: 2026-05-31
Posted: 2026-05-31
Review cadence: Re-scan ENEX inventory after each import release and monthly during active migration.
Source scanned: `~/Downloads/imports/Notebooks/*.enex`

## Scan Summary

- ENEX files scanned: 7
- Total notes: 4705
- Notes with resources: 1278
- Notes with tags: 4468
- Notes with note-attributes: 4705
- Embedded Evernote links (`evernote:`): 22933
- HTTP/HTTPS links: 18633

## Per-Notebook Breakdown

| File | Notes | Resources | Evernote links | HTTP links | task elements |
| --- | ---: | ---: | ---: | ---: | ---: |
| Decisions.enex | 2966 | 1823 | 15968 | 8477 | 61 |
| Employment.enex | 211 | 181 | 858 | 273 | 0 |
| Enduring.enex | 208 | 283 | 1213 | 1042 | 37 |
| EvernoteEncryption.enex | 149 | 39 | 339 | 122 | 1 |
| GodContent2ndexport.enex | 13 | 0 | 108 | 4 | 0 |
| LimitedShelfLife.enex | 98 | 93 | 196 | 36 | 0 |
| Research.enex | 1060 | 986 | 4251 | 8679 | 6 |

## Note Top-Level Elements Seen

| Element | Occurrences |
| --- | ---: |
| title | 4705 |
| created | 4705 |
| updated | 4705 |
| note-attributes | 4705 |
| content | 4705 |
| tag | 15220 |
| resource | 3405 |
| task | 105 |

## Note-Attributes Subfields Seen

| note-attributes field | Occurrences |
| --- | ---: |
| author | 4191 |
| source | 4077 |
| source-url | 445 |
| source-application | 284 |
| reminder-order | 34 |
| content-class | 31 |
| reminder-time | 30 |
| reminder-done-time | 24 |
| subject-date | 12 |

## Resource Metadata Seen

### Resource-level fields

| resource field | Occurrences |
| --- | ---: |
| data | 3405 |
| mime | 3405 |
| resource-attributes | 3405 |
| resource-attributes.file-name | 3405 |
| resource-attributes.source-url | 3405 |
| width | 2606 |
| height | 2606 |

### Resource MIME types observed

| MIME type | Count |
| --- | ---: |
| image/png | 1569 |
| image/jpeg | 845 |
| application/pdf | 461 |
| image/gif | 127 |
| image/tiff | 69 |
| application/octet-stream | 68 |
| application/msword | 51 |
| application/vnd.openxmlformats-officedocument.wordprocessingml.document | 51 |
| application/vnd.openxmlformats-officedocument.presentationml.presentation | 51 |
| application/vnd.openxmlformats-officedocument.spreadsheetml.sheet | 33 |
| application/x-iwork-keynote-sffkey | 24 |
| application/vnd.ms-powerpoint | 8 |
| application/vnd.ms-excel.sheet.macroenabled.12 | 8 |
| image/svg+xml | 8 |
| application/zip | 6 |
| text/csv | 6 |
| image/heic | 4 |
| application/x-iwork-pages-sffpages | 4 |
| video/mp4 | 2 |
| image/PNG | 2 |
| image/GIF | 2 |
| image/JPG | 2 |
| application/x-iwork-numbers-sffnumbers | 2 |
| image/bmp | 1 |
| audio/mpeg | 1 |

## ENML Structural Tags (Top Seen)

| Tag | Count |
| --- | ---: |
| div | 202469 |
| span | 110917 |
| li | 59428 |
| br | 49874 |
| a | 43310 |
| td | 29784 |
| b | 16219 |
| ul | 13257 |
| tr | 9959 |
| u | 9494 |
| p | 6758 |
| en-note | 4705 |
| code | 4311 |
| en-media | 3833 |
| en-todo | 2669 |
| table | 1169 |
| pre | 471 |
| blockquote | 121 |
| en-crypt | 1 |

## Evernote -> Notion Gap Matrix

This matrix distinguishes:

- Notion API support (platform capability)
- Current e2n support (implemented behavior today)

| Evernote export type | Notion API support | Current e2n support | Gap / action |
| --- | --- | --- | --- |
| Note title, created, updated | Yes | Yes (title/tags currently strongest) | Expand DB schema for full metadata parity |
| Tags | Yes (multi-select) | Yes | Keep |
| note-attributes.author/source/source-url/source-application | Yes (text/url properties) | Partial | Add property mapping per import DB schema |
| note-attributes reminders and subject-date | Partial (representable as numbers/dates/text) | Not fully mapped | Add mappings or track in exceptions where semantics differ |
| ENML plain text formatting (p/div/span/b/i/u etc.) | Yes (rich_text blocks) | Partial | Continue conversion hardening |
| HTTP/HTTPS links | Yes | Yes (Phase 1 inline link segments) | Keep |
| Evernote embedded note links (`evernote:`) | No native Evernote concept | Deferred via callout + exception | Implement post-import resolver + manual resolution UI |
| en-media images | Yes | Yes (URL-backed path) | Add upload-backed path for local binaries |
| en-media PDFs | Yes | Yes (URL-backed path) | Add upload-backed path for local binaries |
| Generic files (doc/docx/zip/csv/octet-stream) | Yes | Partial | Wire full file_upload flow end-to-end |
| Audio/video attachments | API has block types, but ingestion constraints apply | Currently unsupported by policy | Keep exception workflow until robust upload support is validated |
| ENML tables (table/tr/td) | API has table/table_row blocks | Currently unsupported by policy | Implement table converter with safe fallback |
| task element (top-level ENEX) | Unknown mapping in current pipeline | Not mapped | Define explicit handling rule and exception reason |
| en-crypt | Not directly decryptable by API | Not mapped | Preserve marker + manual recovery record |

## Post-Import Exception Management Protocol

All gaps require a managed post-import path. No exceptions are allowed to remain
untracked.

### Mandatory exception lifecycle

1. Detect: importer flags the gap at note/block/property level.
2. Record: create durable exception record in local state and Notion exceptions DB.
3. Link: associate exception to the exact Notion target (page or marker block URL/ID).
4. Classify: assign reason code (`Unsupported Content`, `Evernote Link`, `Attribute Gap`, etc.).
5. Route:
	 - Programmatic remediation queue when deterministic recovery exists.
	 - Manual remediation queue when human choice is required.
6. Resolve: apply fix and persist resolution metadata (`resolved_by`, `resolved_at`, `resolution_method`).
7. Verify: run state check to confirm the note is now in expected final state.
8. Close: mark exception `closed` only after verification passes.

### Required exception fields

- `run_id`
- `source_file`
- `note_id`
- `note_title`
- `exception_type`
- `reason`
- `severity`
- `notion_target_type` and `notion_target_id`
- `error_message`
- `external_resource_ref` (when applicable)
- `status` (`open`, `in_progress`, `resolved`, `closed`, `dismissed`)
- `created_at`, `updated_at`, `resolved_at`

### Management protocol SLAs

- `open` exceptions must be visible in UI and exportable as CSV/JSON.
- Severity `high` exceptions require remediation plan assignment before run closeout.
- A run cannot be marked `complete` when reconciliation invariants fail:
	`total_notes == imported_ok + imported_with_exceptions`.

## Re-Run Content Review and State Verification Protocol

The system must support repeatable re-review runs to validate current note state
after remediation and after parser/importer updates.

### Re-review triggers

- new importer release
- Notion API version change
- updated gap mapping logic
- manual remediation batch complete

### Verification checks per note

1. Existence: expected Notion row/page exists.
2. Metadata parity: mapped fields match source note metadata snapshot.
3. Block integrity: block sequence fingerprint matches latest expected transform result.
4. Exception integrity: all open exceptions still reference valid note/block targets.
5. Link integrity: resolved embedded links still point to existing target pages.

### State model

- `not_reviewed`
- `review_passed`
- `review_failed`
- `review_passed_with_open_exceptions`

Store `last_reviewed_at`, `review_version`, `review_result`, and `review_diff`
for each note to support auditability.

## Phase 2 and Phase 3 Implementation Checklist (Tracked)

Status key: `[ ]` not started, `[~]` in progress, `[x]` done.

### Phase 2 (Core post-import management)

- [ ] P2-01: Exception schema hardening in state DB (required fields + indexes).
- [ ] P2-02: Exception ingestion path from importer events (all gap classes).
- [ ] P2-03: Exception dashboard filters (reason, severity, source file, status).
- [ ] P2-04: Programmatic remediation queue engine.
- [ ] P2-05: Manual remediation workflow hooks (`assign`, `resolve`, `dismiss`).
- [ ] P2-06: Run reconciliation gate (`No note left behind` invariant enforcement).
- [ ] P2-07: Export endpoints for exception reports (CSV/JSON).

### Phase 3 (Re-review and state verification)

- [ ] P3-01: Re-review runner (full run and selective note subsets).
- [ ] P3-02: Note state fingerprinting for content/block parity checks.
- [ ] P3-03: Embedded link re-validation pass (resolved links and orphan detection).
- [ ] P3-04: Review result persistence (`review_version`, diffs, timestamps).
- [ ] P3-05: UI status surfaces for note state and review outcomes.
- [ ] P3-06: Automated regression report between successive review runs.

### Ticketization guidance

- Use one ticket per checklist item (`P2-xx`, `P3-xx`) in your issue tracker.
- Each ticket should include: acceptance criteria, test coverage requirements, and
	migration impact notes.

## Prioritized Gaps for This Dataset

1. Evernote internal links (22933 occurrences) are the largest functional gap and need resolver tooling.
2. Table conversion (1169 table tags) is high value for preserving structure in technical/research notes.
3. Attachment coverage beyond images/PDFs should be upgraded via File Upload APIs, especially office docs and presentation files.
4. Reminder/task metadata should be mapped or explicitly surfaced in exceptions to avoid silent semantic loss.
