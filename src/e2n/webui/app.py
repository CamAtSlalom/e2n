"""FastAPI application for local e2n operations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from e2n.cli import run_notion_import
from e2n.enex import extract_enex_notes
from e2n.notion import (
    NotionClient,
    bootstrap_notion_pages,
    ensure_import_database,
    ensure_exception_database,
)
from e2n.state import ProcessingStateStore


@dataclass(frozen=True)
class RunCard:
    """Dashboard summary for one source processing directory."""

    source_name: str
    output_directory: str
    state_path: str
    latest_run_id: str | None
    note_count: int
    extracted_count: int
    extraction_error_count: int
    committed_count: int
    pending_count: int
    failed_count: int


def create_app() -> FastAPI:
    """Build and return the local web UI application."""
    app = FastAPI(title="e2n Local UI", version="0.1.0")
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
    app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request, processing_dir: str = "./processing", message: str = "", error: str = "") -> HTMLResponse:
        processing_directory = Path(processing_dir).expanduser().resolve()
        cards = _collect_run_cards(processing_directory)
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "processing_dir": str(processing_directory),
                "cards": cards,
                "message": message,
                "error": error,
            },
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/extract")
    def extract(
        enex_source: str = Form(...),
        processing_dir: str = Form(...),
    ) -> RedirectResponse:
        try:
            source = Path(enex_source).expanduser().resolve()
            output_parent = Path(processing_dir).expanduser().resolve()
            if source.is_dir():
                sources = sorted(path for path in source.iterdir() if path.is_file() and path.suffix.lower() == ".enex")
                if not sources:
                    raise FileNotFoundError(f"No .enex files found in source directory: {source}")
                for enex_file in sources:
                    extract_enex_notes(enex_file, output_parent)
            else:
                extract_enex_notes(source, output_parent)
            return _redirect_with_message(processing_dir, "Extraction complete")
        except Exception as exc:
            return _redirect_with_error(processing_dir, str(exc))

    @app.post("/import")
    def import_notes(
        enex_source: str = Form(...),
        processing_dir: str = Form(...),
        notion_key: str = Form(...),
        notion_root: str = Form(""),
        resume: str | None = Form(None),
    ) -> RedirectResponse:
        try:
            args = _build_notion_import_args(
                enex_source=enex_source,
                processing_dir=processing_dir,
                notion_key=notion_key,
                notion_root=notion_root or None,
                resume=resume == "on",
            )
            run_notion_import(args)
            return _redirect_with_message(processing_dir, "Import execution complete")
        except Exception as exc:
            return _redirect_with_error(processing_dir, str(exc))

    @app.post("/run-control")
    def run_control(
        action: str = Form(...),
        run_id: str = Form(...),
        enex_source: str = Form(...),
        processing_dir: str = Form(...),
        notion_key: str = Form(""),
        notion_root: str = Form(""),
    ) -> RedirectResponse:
        try:
            if action not in {"reset", "wipe-local", "wipe-remote"}:
                raise ValueError(f"Unsupported action: {action}")
            args = _build_notion_import_args(
                enex_source=enex_source,
                processing_dir=processing_dir,
                notion_key=notion_key,
                notion_root=notion_root or None,
                resume=False,
                reset_run=run_id if action == "reset" else None,
                wipe_local=run_id if action == "wipe-local" else None,
                wipe_remote=run_id if action == "wipe-remote" else None,
            )
            run_notion_import(args)
            return _redirect_with_message(processing_dir, f"Run control completed: {action}")
        except Exception as exc:
            return _redirect_with_error(processing_dir, str(exc))

    # --- Wizard routes ---

    # In-memory wizard state (per-process; sufficient for single-user local tool)
    _wizard_state: dict[str, str] = {}

    @app.get("/wizard/", response_class=HTMLResponse)
    def wizard_root(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request,
            name="wizard_step1.html",
            context={"error": ""},
        )

    @app.post("/wizard/step/1")
    def wizard_step_1_post(
        request: Request,
        enex_source: str = Form(...),
        processing_directory: str = Form(...),
    ):
        source_path = Path(enex_source).expanduser().resolve()
        if not source_path.exists():
            return templates.TemplateResponse(
                request=request,
                name="wizard_step1.html",
                context={"error": f"Source does not exist: {source_path}"},
            )
        _wizard_state["enex_source"] = str(source_path)
        _wizard_state["processing_directory"] = processing_directory
        _wizard_state["step1_complete"] = "true"
        return RedirectResponse(url="/wizard/step/2", status_code=303)

    @app.get("/wizard/step/2", response_class=HTMLResponse)
    def wizard_step_2(request: Request):
        if _wizard_state.get("step1_complete") != "true":
            return RedirectResponse(url="/wizard/", status_code=303)
        return templates.TemplateResponse(
            request=request,
            name="wizard_step2.html",
            context={"error": "", "success": ""},
        )

    @app.post("/wizard/step/2", response_class=HTMLResponse)
    def wizard_step_2_post(
        request: Request,
        notion_key: str = Form(...),
        notion_root: str = Form(""),
    ):
        try:
            client = NotionClient(notion_key)
            client.search_pages()
            _wizard_state["notion_key"] = notion_key
            _wizard_state["notion_root"] = notion_root
            _wizard_state["step2_complete"] = "true"
            return templates.TemplateResponse(
                request=request,
                name="wizard_step2.html",
                context={"error": "", "success": "Connected successfully."},
            )
        except Exception as exc:
            return templates.TemplateResponse(
                request=request,
                name="wizard_step2.html",
                context={"error": f"Connection failed: {exc}", "success": ""},
            )

    @app.get("/wizard/step/3", response_class=HTMLResponse)
    def wizard_step_3(request: Request):
        if _wizard_state.get("step2_complete") != "true":
            return RedirectResponse(url="/wizard/step/2", status_code=303)
        return templates.TemplateResponse(
            request=request,
            name="wizard_step3.html",
            context={"error": ""},
        )

    @app.post("/wizard/step/3")
    def wizard_step_3_post(request: Request):
        if _wizard_state.get("step2_complete") != "true":
            return RedirectResponse(url="/wizard/step/2", status_code=303)
        try:
            source = Path(_wizard_state["enex_source"])
            proc_dir = Path(_wizard_state["processing_directory"])
            extract_enex_notes(source, proc_dir)
            _wizard_state["step3_complete"] = "true"
            return RedirectResponse(url="/wizard/step/4", status_code=303)
        except Exception as exc:
            return templates.TemplateResponse(
                request=request,
                name="wizard_step3.html",
                context={"error": str(exc)},
            )

    @app.get("/wizard/step/4", response_class=HTMLResponse)
    def wizard_step_4(request: Request):
        if _wizard_state.get("step3_complete") != "true":
            return RedirectResponse(url="/wizard/step/3", status_code=303)
        return templates.TemplateResponse(
            request=request,
            name="wizard_step4.html",
            context={"error": ""},
        )

    @app.post("/wizard/step/4")
    def wizard_step_4_post(request: Request):
        if _wizard_state.get("step3_complete") != "true":
            return RedirectResponse(url="/wizard/step/3", status_code=303)
        try:
            source = Path(_wizard_state["enex_source"])
            proc_dir = Path(_wizard_state["processing_directory"])
            notion_key = _wizard_state.get("notion_key", "")
            notion_root = _wizard_state.get("notion_root") or None

            from e2n.enex import discover_enex_sources
            from e2n.enml import plan_enml_segments
            from e2n.notion import segments_to_notion_blocks

            client = NotionClient(notion_key)
            bootstrap = bootstrap_notion_pages(notion_key, root_title=notion_root)
            sources = discover_enex_sources(source)

            for src in sources:
                output_dir = proc_dir.expanduser().resolve() / src.stem
                state_path = output_dir / "state.db"
                if not state_path.exists():
                    continue
                import_db = ensure_import_database(client, bootstrap.converted.page_id, src.stem)
                exc_db = ensure_exception_database(client, bootstrap.exceptions.page_id)

                store = ProcessingStateStore(state_path)
                try:
                    run_id = store.latest_run_id()
                    if not run_id:
                        continue
                    notes = store.list_notes(run_id, status="extracted")
                    for note in notes:
                        note_file = output_dir / "notes" / f"{note.note_id}.enex"
                        if not note_file.exists():
                            continue
                        from lxml import etree
                        tree = etree.parse(str(note_file), parser=etree.XMLParser(recover=True))
                        root = tree.getroot()
                        note_el = root.find("note") if root.tag != "note" else root
                        content_el = note_el.find("content") if note_el is not None else None
                        content_text = content_el.text or "" if content_el is not None else ""

                        segments = plan_enml_segments(content_text)
                        blocks, _exc = segments_to_notion_blocks(
                            segments, {}, note_id=note.note_id, note_title=note.title
                        )
                        client.import_note_blocks(
                            database_id=import_db.database_id,
                            title=note.title,
                            tags=tuple(note.tags),
                            blocks=blocks,
                        )
                finally:
                    store.close()

            _wizard_state["step4_complete"] = "true"
            return RedirectResponse(url="/wizard/step/5", status_code=303)
        except Exception as exc:
            return templates.TemplateResponse(
                request=request,
                name="wizard_step4.html",
                context={"error": str(exc)},
            )

    @app.get("/wizard/step/5", response_class=HTMLResponse)
    def wizard_step_5(request: Request):
        if _wizard_state.get("step4_complete") != "true" and _wizard_state.get("step3_complete") != "true":
            return RedirectResponse(url="/wizard/step/4", status_code=303)
        # Collect exception summary from processing directories
        proc_dir = Path(_wizard_state.get("processing_directory", "")).expanduser().resolve()
        exceptions_summary: list[dict] = []
        if proc_dir.exists():
            for child in proc_dir.iterdir():
                exc_file = child / "exceptions.txt" if child.is_dir() else None
                if exc_file and exc_file.exists():
                    lines = exc_file.read_text(encoding="utf-8").strip().splitlines()
                    for line in lines:
                        parts = line.split("\t")
                        if len(parts) >= 3:
                            exceptions_summary.append({
                                "note_id": parts[0],
                                "title": parts[1],
                                "reasons": parts[2],
                            })
        return templates.TemplateResponse(
            request=request,
            name="wizard_step5.html",
            context={"exceptions": exceptions_summary, "total": len(exceptions_summary)},
        )

    @app.get("/wizard/progress")
    def wizard_progress():
        proc_dir = _wizard_state.get("processing_directory", "")
        if not proc_dir:
            return {"status": "not_started", "total_notes": 0, "processed": 0, "current": ""}
        proc_path = Path(proc_dir).expanduser().resolve()
        # Scan for state.db files in processing subdirectories
        total = 0
        processed = 0
        for child in proc_path.iterdir() if proc_path.exists() else []:
            state_path = child / "state.db" if child.is_dir() else None
            if state_path and state_path.exists():
                store = ProcessingStateStore(state_path)
                try:
                    run_id = store.latest_run_id()
                    if run_id:
                        counts = store.count_operations_by_status(run_id)
                        total += counts.get("pending", 0) + counts.get("committed", 0) + counts.get("failed", 0)
                        processed += counts.get("committed", 0)
                finally:
                    store.close()
        status = "complete" if total > 0 and processed == total else "in_progress" if processed > 0 else "not_started"
        return {"status": status, "total_notes": total, "processed": processed, "current": ""}

    return app


def _build_notion_import_args(
    enex_source: str,
    processing_dir: str,
    notion_key: str,
    notion_root: str | None,
    resume: bool,
    reset_run: str | None = None,
    wipe_local: str | None = None,
    wipe_remote: str | None = None,
) -> object:
    """Build a namespace-like object accepted by run_notion_import."""

    class Args:
        pass

    args = Args()
    args.enex_source = Path(enex_source).expanduser().resolve()
    args.processing_directory = Path(processing_dir).expanduser().resolve()
    args.notion_key = notion_key
    args.notion_root = notion_root
    args.resume = resume
    args.reset_run = reset_run
    args.wipe_local = wipe_local
    args.wipe_remote = wipe_remote
    return args


def _collect_run_cards(processing_directory: Path) -> list[RunCard]:
    """Return dashboard cards for each processing child with durable state."""
    if not processing_directory.exists() or not processing_directory.is_dir():
        return []

    cards: list[RunCard] = []
    for child in sorted(path for path in processing_directory.iterdir() if path.is_dir()):
        state_path = child / "state.db"
        if not state_path.exists():
            continue

        store = ProcessingStateStore(state_path)
        try:
            latest_run = store.latest_run_id()
            note_count = 0
            extracted_count = 0
            extraction_error_count = 0
            committed_count = 0
            pending_count = 0
            failed_count = 0
            if latest_run is not None:
                notes = store.list_notes(latest_run)
                counts = store.count_operations_by_status(latest_run)
                note_count = len(notes)
                extracted_count = sum(1 for note in notes if note.status == "extracted")
                extraction_error_count = sum(1 for note in notes if note.status == "extraction_error")
                committed_count = counts.get("committed", 0)
                pending_count = counts.get("pending", 0)
                failed_count = counts.get("failed", 0)

            cards.append(
                RunCard(
                    source_name=child.name,
                    output_directory=str(child),
                    state_path=str(state_path),
                    latest_run_id=latest_run,
                    note_count=note_count,
                    extracted_count=extracted_count,
                    extraction_error_count=extraction_error_count,
                    committed_count=committed_count,
                    pending_count=pending_count,
                    failed_count=failed_count,
                )
            )
        finally:
            store.close()

    return cards


def _redirect_with_message(processing_dir: str, message: str) -> RedirectResponse:
    target = "/?" + urlencode({"processing_dir": processing_dir, "message": message})
    return RedirectResponse(url=target, status_code=303)


def _redirect_with_error(processing_dir: str, error: str) -> RedirectResponse:
    target = "/?" + urlencode({"processing_dir": processing_dir, "error": error})
    return RedirectResponse(url=target, status_code=303)
