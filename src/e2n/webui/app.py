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
            context={"error": ""},
        )

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
