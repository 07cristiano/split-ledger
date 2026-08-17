"""SplitLedger FastAPI application factory."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.config import load_local_env
from app.db import initialize_database, is_postgres_database
from app.parsers.gemini import GeminiParserAdapter
from app.parsers.mock import DraftParseError, MockParserAdapter
from app.repositories import (
    DEMO_PASSWORD,
    create_equal_split_expense,
    create_group,
    fetch_group_for_member,
    fetch_user,
    fetch_user_by_name,
    group_balances,
    list_expenses,
    list_group_members,
    list_groups_for_user,
    list_users,
    seed_demo_data,
    today_iso,
)
from app.security import verify_password
from app.services.money import MoneyValidationError, format_paise, paise_input_value, parse_paise
from app.services.settlement import settlement_plan


PACKAGE_DIR = Path(__file__).resolve().parent
load_local_env(PACKAGE_DIR.parent / ".env")
DEFAULT_DB_PATH = PACKAGE_DIR.parent / "data" / "splitledger.db"
DEVELOPMENT_SESSION_SECRET = "splitledger-development-secret-change-me"
EXAMPLE_SESSION_SECRET = "replace-this-with-a-long-random-development-secret"


def environment_flag(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def is_production_environment() -> bool:
    """Recognize explicit production settings and Vercel runtime environments."""
    app_environment = os.getenv("APP_ENV", "").strip().lower()
    vercel_environment = os.getenv("VERCEL_ENV", "").strip().lower()
    return (
        app_environment == "production"
        or os.getenv("VERCEL") == "1"
        or vercel_environment in {"production", "preview"}
    )


def resolve_database_target(db_path: str | Path | None = None) -> str | Path:
    """Use an explicit test path, persistent DATABASE_URL, or local SQLite in that order."""
    if db_path is not None:
        return db_path
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        if is_production_environment() and not is_postgres_database(database_url):
            raise RuntimeError("DATABASE_URL must be a PostgreSQL URL in production.")
        return database_url
    if is_production_environment():
        raise RuntimeError(
            "DATABASE_URL is required in production because the serverless filesystem cannot persist SQLite."
        )
    return Path(os.getenv("SPLITLEDGER_DB_PATH", DEFAULT_DB_PATH))


def create_app(
    db_path: str | Path | None = None,
    seed: bool = True,
    parser_mode: str | None = None,
) -> FastAPI:
    production_mode = is_production_environment()
    session_secret = os.getenv("SESSION_SECRET", "").strip()
    if production_mode and session_secret in {
        "",
        DEVELOPMENT_SESSION_SECRET,
        EXAMPLE_SESSION_SECRET,
    }:
        raise RuntimeError("Set a long, private SESSION_SECRET before running SplitLedger in production.")

    database_path = resolve_database_target(db_path)
    initialize_database(database_path)
    if seed:
        seed_demo_data(database_path)

    app = FastAPI(title="SplitLedger", version="0.1.0")
    app.state.db_path = database_path
    app.state.parser_mode = (parser_mode or os.getenv("PARSER_MODE", "mock")).strip().lower()
    app.add_middleware(
        SessionMiddleware,
        secret_key=session_secret or DEVELOPMENT_SESSION_SECRET,
        https_only=production_mode,
        same_site="lax",
    )
    app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")
    templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")
    templates.env.filters["money"] = format_paise

    def current_user_id(request: Request) -> int | None:
        value = request.session.get("user_id")
        return int(value) if value is not None else None

    def redirect_to_login() -> RedirectResponse:
        return RedirectResponse("/login", status_code=303)

    def require_group_member(request: Request, group_id: int):
        user_id = current_user_id(request)
        if user_id is None:
            return None, redirect_to_login()
        group = fetch_group_for_member(database_path, group_id, user_id)
        if group is None:
            return None, RedirectResponse("/groups?error=You+cannot+access+that+group", status_code=303)
        return group, None

    def template_context(request: Request, group_id: int, group, error: str | None = None) -> dict:
        user_id = current_user_id(request)
        assert user_id is not None
        members = list_group_members(database_path, group_id)
        balances = group_balances(database_path, group_id)
        balance_map = {int(row["id"]): int(row["balance_paise"]) for row in balances}
        name_by_id = {int(row["id"]): row["display_name"] for row in members}
        transfers = [
            {
                "from_name": name_by_id[transfer.from_user_id],
                "to_name": name_by_id[transfer.to_user_id],
                "amount_paise": transfer.amount_paise,
            }
            for transfer in settlement_plan(balance_map)
        ]
        return {
            "group": group,
            "members": members,
            "balances": balances,
            "expenses": list_expenses(database_path, group_id),
            "transfers": transfers,
            "current_user": fetch_user(database_path, user_id),
            "today": today_iso(),
            "error": error,
            "parser_mode": app.state.parser_mode,
        }

    def parser_adapter() -> MockParserAdapter | GeminiParserAdapter:
        """Choose a parser mode without changing the trusted save path."""
        mode = app.state.parser_mode
        if mode == "mock":
            return MockParserAdapter()
        if mode == "gemini":
            return GeminiParserAdapter(
                api_key=os.getenv("GEMINI_API_KEY", ""),
                model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            )
        raise DraftParseError("PARSER_MODE must be either 'mock' or 'gemini'.")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request) -> RedirectResponse:
        return RedirectResponse("/groups" if current_user_id(request) else "/login", status_code=303)

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request, error: str | None = None):
        if current_user_id(request):
            return RedirectResponse("/groups", status_code=303)
        return templates.TemplateResponse(
            request,
            "login.html",
            {"users": list_users(database_path), "error": error, "demo_password": DEMO_PASSWORD},
        )

    @app.post("/login")
    async def login(request: Request, display_name: str = Form(...), password: str = Form(...)):
        user = fetch_user_by_name(database_path, display_name)
        if user is None or not verify_password(password, user["password_hash"]):
            return RedirectResponse("/login?error=Invalid+display+name+or+password", status_code=303)
        request.session.clear()
        request.session["user_id"] = int(user["id"])
        return RedirectResponse("/groups", status_code=303)

    @app.post("/logout")
    async def logout(request: Request):
        request.session.clear()
        return RedirectResponse("/login", status_code=303)

    @app.get("/groups", response_class=HTMLResponse)
    async def groups_page(request: Request, error: str | None = None):
        user_id = current_user_id(request)
        if user_id is None:
            return redirect_to_login()
        users = list_users(database_path)
        current_user = next(user for user in users if int(user["id"]) == user_id)
        return templates.TemplateResponse(
            request,
            "groups.html",
            {
                "groups": list_groups_for_user(database_path, user_id),
                "users": users,
                "current_user": current_user,
                "error": error,
            },
        )

    @app.post("/groups")
    async def create_group_route(request: Request):
        user_id = current_user_id(request)
        if user_id is None:
            return redirect_to_login()
        form = await request.form()
        name = str(form.get("name", "")).strip()
        raw_member_ids = form.getlist("member_ids")
        try:
            member_ids = [int(item) for item in raw_member_ids]
        except ValueError:
            return RedirectResponse("/groups?error=Invalid+member+selection", status_code=303)
        valid_ids = {int(user["id"]) for user in list_users(database_path)}
        if not name or len(name) > 80 or not set(member_ids).issubset(valid_ids):
            return RedirectResponse("/groups?error=Enter+a+valid+group+and+members", status_code=303)
        group_id = create_group(database_path, name, user_id, member_ids)
        return RedirectResponse(f"/groups/{group_id}", status_code=303)

    @app.get("/groups/{group_id}", response_class=HTMLResponse)
    async def group_dashboard(request: Request, group_id: int, error: str | None = None):
        group, redirect = require_group_member(request, group_id)
        if redirect:
            return redirect
        return templates.TemplateResponse(request, "dashboard.html", template_context(request, group_id, group, error))

    @app.get("/groups/{group_id}/expenses/new", response_class=HTMLResponse)
    async def new_expense_page(request: Request, group_id: int):
        group, redirect = require_group_member(request, group_id)
        if redirect:
            return redirect
        return templates.TemplateResponse(request, "expense_form.html", template_context(request, group_id, group))

    @app.post("/groups/{group_id}/expenses/new")
    async def create_expense_route(request: Request, group_id: int):
        group, redirect = require_group_member(request, group_id)
        if redirect:
            return redirect
        form = await request.form()
        try:
            payer_id = int(str(form.get("payer_id", "")))
            participant_ids = [int(value) for value in form.getlist("participant_ids")]
            amount_paise = parse_paise(str(form.get("amount", "")))
            create_equal_split_expense(
                database_path,
                group_id=group_id,
                actor_id=int(current_user_id(request)),
                payer_id=payer_id,
                amount_paise=amount_paise,
                description=str(form.get("description", "")),
                expense_date=str(form.get("expense_date", "")),
                participant_ids=participant_ids,
            )
        except (ValueError, MoneyValidationError, PermissionError) as error:
            context = template_context(request, group_id, group, str(error))
            context["submitted"] = form
            return templates.TemplateResponse(request, "expense_form.html", context, status_code=422)
        return RedirectResponse(f"/groups/{group_id}", status_code=303)

    @app.get("/groups/{group_id}/expense-drafts/new", response_class=HTMLResponse)
    async def new_draft_page(request: Request, group_id: int):
        group, redirect = require_group_member(request, group_id)
        if redirect:
            return redirect
        return templates.TemplateResponse(request, "draft_form.html", template_context(request, group_id, group))

    @app.post("/groups/{group_id}/expense-drafts")
    async def create_draft_route(request: Request, group_id: int):
        group, redirect = require_group_member(request, group_id)
        if redirect:
            return redirect
        form = await request.form()
        raw_input = str(form.get("raw_input", ""))
        context = template_context(request, group_id, group)
        try:
            members_by_id = {int(member["id"]): member["display_name"] for member in context["members"]}
            draft = await parser_adapter().parse(raw_input, members_by_id, int(current_user_id(request)))
        except DraftParseError as error:
            context["error"] = str(error)
            context["raw_input"] = raw_input
            return templates.TemplateResponse(request, "draft_form.html", context, status_code=422)
        context["draft_values"] = {
            "raw_input": draft.raw_input,
            "description": draft.description,
            "amount": paise_input_value(draft.amount_paise),
            "expense_date": draft.expense_date,
            "payer_id": str(draft.payer_id),
            "participant_ids": [str(member_id) for member_id in draft.participant_ids],
        }
        return templates.TemplateResponse(request, "draft_review.html", context)

    @app.post("/groups/{group_id}/expense-drafts/confirm")
    async def confirm_draft_route(request: Request, group_id: int):
        group, redirect = require_group_member(request, group_id)
        if redirect:
            return redirect
        form = await request.form()
        context = template_context(request, group_id, group)
        try:
            payer_id = int(str(form.get("payer_id", "")))
            participant_ids = [int(value) for value in form.getlist("participant_ids")]
            create_equal_split_expense(
                database_path,
                group_id=group_id,
                actor_id=int(current_user_id(request)),
                payer_id=payer_id,
                amount_paise=parse_paise(str(form.get("amount", ""))),
                description=str(form.get("description", "")),
                expense_date=str(form.get("expense_date", "")),
                participant_ids=participant_ids,
                input_mode="text_draft",
                raw_input=str(form.get("raw_input", "")),
            )
        except (ValueError, MoneyValidationError, PermissionError) as error:
            context["error"] = str(error)
            context["draft_values"] = {
                "raw_input": str(form.get("raw_input", "")),
                "description": str(form.get("description", "")),
                "amount": str(form.get("amount", "")),
                "expense_date": str(form.get("expense_date", "")),
                "payer_id": str(form.get("payer_id", "")),
                "participant_ids": [str(value) for value in form.getlist("participant_ids")],
            }
            return templates.TemplateResponse(request, "draft_review.html", context, status_code=422)
        return RedirectResponse(f"/groups/{group_id}", status_code=303)

    return app


app = create_app(seed=environment_flag("SEED_DEMO_DATA", True))
