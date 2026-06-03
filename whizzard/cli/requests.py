"""`whiz requests` — review and act on agent-initiated capability requests.

Stage 14 / D-165. The in-cell MCP server lets a contained agent request a
mount or a duration extension; those land as JSON files in the per-session
request channel. This is the operator's surface for them:

    whiz requests                 list pending requests (all sessions)
    whiz requests list --all      include already-resolved requests
    whiz requests approve <id>    approve + apply one request
    whiz requests deny <id>       decline one request

`approve` routes through the Stage 13 stop+restart — so, like `whiz adjust`,
the operator's terminal becomes the relaunched session.
"""

from __future__ import annotations

from typing import Annotated

import typer
from rich.table import Table

from whizzard.cli._shared import console
from whizzard.cli.adjust import tty_approver
from whizzard.requests import find_request, mark_resolved, process_request, read_all_requests

requests_app = typer.Typer(
    help="Review agent-initiated capability requests.",
    no_args_is_help=False,
)

_STATUS_STYLE = {
    "pending": "[yellow]pending[/yellow]",
    "applied": "[green]applied[/green]",
    "denied": "[red]denied[/red]",
    "error": "[red]error[/red]",
}


def _truncate(text: str, limit: int) -> str:
    """Trim free text to fit a table cell."""
    text = text.replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


@requests_app.callback(invoke_without_command=True)
def _requests_default(ctx: typer.Context) -> None:
    """Bare `whiz requests` lists pending requests."""
    if ctx.invoked_subcommand is None:
        requests_list_cmd(show_all=False)


@requests_app.command("list")
def requests_list_cmd(
    show_all: Annotated[
        bool,
        typer.Option("--all", help="Include resolved (applied/denied) requests."),
    ] = False,
) -> None:
    """List agent capability requests across all sessions."""
    reqs = read_all_requests(pending_only=not show_all)
    if not reqs:
        msg = "no agent requests" if show_all else "no pending agent requests"
        console.print(f"[yellow]{msg}[/yellow]")
        return

    table = Table(title="Agent requests" if show_all else "Pending agent requests")
    table.add_column("Request")
    table.add_column("Session")
    table.add_column("Asking for")
    table.add_column("Status")
    table.add_column("Reason")
    for r in reqs:
        table.add_row(
            r.request_id,
            r.session_id[:8],
            r.summary(),
            _STATUS_STYLE.get(r.status, r.status),
            _truncate(r.reason, 48) or "—",
        )
    console.print(table)

    if any(r.status == "pending" for r in reqs):
        console.print(
            "\napprove with [bold]whiz requests approve <request-id>[/bold] "
            "or decline with [bold]whiz requests deny <request-id>[/bold]."
        )


@requests_app.command("approve")
def requests_approve_cmd(
    request_id: Annotated[
        str,
        typer.Argument(help="Request id (from `whiz requests`)."),
    ],
    yes: Annotated[
        bool,
        typer.Option(
            "--yes", "-y",
            help="Skip the confirmation prompt (auto-approve). For scripting.",
        ),
    ] = False,
) -> None:
    """Approve an agent request and apply it via the stop+restart flow.

    Like `whiz adjust`, this stops the existing container and re-launches it
    with the new capability; the harness's on-disk state survives the restart.
    The operator's terminal becomes the relaunched session.
    """
    req = find_request(request_id)
    if req is None:
        console.print(
            f"[red]no request with id {request_id!r}. Run `whiz requests`.[/red]"
        )
        raise typer.Exit(code=2)
    if req.status != "pending":
        console.print(
            f"[yellow]request {request_id} is already {req.status} "
            f"({req.resolution_detail or 'no detail'}).[/yellow]"
        )
        raise typer.Exit(code=1)

    console.print(f"[bold]Agent request:[/bold] {req.summary()}")
    console.print(f"[bold]Session:[/bold] {req.session_id}")
    console.print(f"[bold]Agent's reason:[/bold] {req.reason or '(none given)'}")

    approver = (lambda _diff: True) if yes else tty_approver
    result = process_request(req, approver)

    if result.detail:
        colour = (
            "green" if result.exit_code == 0
            else "yellow" if result.exit_code == 1
            else "red"
        )
        console.print(f"[{colour}]{result.detail}[/{colour}]")
    raise typer.Exit(code=result.exit_code)


@requests_app.command("deny")
def requests_deny_cmd(
    request_id: Annotated[
        str,
        typer.Argument(help="Request id (from `whiz requests`)."),
    ],
    reason: Annotated[
        str | None,
        typer.Option("--reason", help="Optional note recorded with the denial."),
    ] = None,
) -> None:
    """Decline an agent request without applying it."""
    req = find_request(request_id)
    if req is None:
        console.print(
            f"[red]no request with id {request_id!r}. Run `whiz requests`.[/red]"
        )
        raise typer.Exit(code=2)
    if req.status != "pending":
        console.print(
            f"[yellow]request {request_id} is already {req.status}.[/yellow]"
        )
        raise typer.Exit(code=1)

    detail = reason or "declined by operator"
    mark_resolved(req, "denied", detail)
    console.print(f"[yellow]denied request {request_id}: {detail}[/yellow]")
