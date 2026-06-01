"""InferGuard CLI."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

app = typer.Typer(
    name="inferguard",
    help="Standalone-first inference monitoring for vLLM and SGLang endpoints.",
    no_args_is_help=True,
)
console = Console()


def _load_runtime_config(endpoint: str | None = None):
    if endpoint:
        os.environ["TARGET_ENDPOINT"] = endpoint
    from inferguard.config import InferGuardConfig

    return InferGuardConfig.from_env()


def _print_report(report: dict[str, Any]) -> None:
    status = report.get("status", "unknown")

    if status == "healthy":
        console.print("[green]Endpoint is healthy.[/green]")
        console.print(Syntax(json.dumps(report["metrics"], indent=2), "json", theme="monokai"))
        return

    if status == "anomaly_detected":
        anomaly = report["anomaly"]
        diagnosis = report["diagnosis"]
        remediation = report["remediation"]

        console.print(f"[red]ANOMALY: {anomaly['severity']}[/red]")
        for reason in anomaly["reasons"]:
            console.print(f"  - {reason}")
        console.print(f"\n[yellow]Diagnosis:[/yellow] {diagnosis['root_cause']}")
        console.print(f"[yellow]Failure mode:[/yellow] {diagnosis['failure_mode']}")
        console.print(f"[yellow]Confidence:[/yellow] {diagnosis['confidence']:.0%}")
        console.print(f"[yellow]Risk:[/yellow] {diagnosis.get('risk_level', 'unknown')}")
        console.print(
            f"[yellow]Actuation recommendation:[/yellow] {diagnosis.get('actuation_recommendation', '') or 'n/a'}"
        )
        console.print("\n[cyan]Recommended fix:[/cyan]")
        console.print(Panel(Syntax(remediation["launch_command"], "bash", theme="monokai")))
        if remediation.get("cost_note"):
            console.print(f"[cyan]Cost note:[/cyan] {remediation['cost_note']}")
        if remediation.get("estimated_capacity_impact_pct") is not None:
            console.print(
                f"[cyan]Estimated capacity impact:[/cyan] {remediation['estimated_capacity_impact_pct']}%"
            )
        if remediation.get("estimated_kv_relief_pct") is not None:
            console.print(
                f"[cyan]Estimated KV relief:[/cyan] {remediation['estimated_kv_relief_pct']}%"
            )
        safe_actions = report.get("safe_actions", [])
        if safe_actions:
            console.print("\n[magenta]Safe actions:[/magenta]")
            for sa in safe_actions:
                action_type = sa.get("action_type", "unknown")
                if sa.get("attempted"):
                    if sa.get("applied"):
                        status = "[green]APPLIED[/green]"
                    else:
                        status = f"[red]FAILED[/red] ({sa.get('execution_error', '?')})"
                    console.print(f"  → {action_type}: {status}")
                    if sa.get("verified"):
                        console.print(f"    Verification: {sa.get('verification_result', '?')}")
                else:
                    console.print(f"  → {action_type}: [yellow]ADVISORY[/yellow]")
        replay_validation = report.get("replay_validation")
        if isinstance(replay_validation, dict):
            console.print("\n[magenta]Replay validation:[/magenta]")
            console.print(Syntax(json.dumps(replay_validation, indent=2), "json", theme="monokai"))
        return

    console.print(f"[red]Error:[/red] {report.get('error', 'unknown')}")


@app.command()
def scan(
    endpoint: str = typer.Argument(help="Inference endpoint URL, e.g. http://localhost:8000"),
    model: str = typer.Option("", help="Optional model name hint; otherwise InferGuard will try /v1/models."),
) -> None:
    """Run one scrape/detect/diagnose/remediate cycle."""
    config = _load_runtime_config(endpoint)
    from inferguard.agent import InferGuardAgent

    async def _scan() -> dict[str, Any]:
        agent = InferGuardAgent(config, model_name=model)
        try:
            return await agent.run_once()
        finally:
            await agent.shutdown()

    report = asyncio.run(_scan())
    _print_report(report)
    if report.get("status") == "error":
        raise typer.Exit(1)


@app.command()
def watch(
    endpoint: str = typer.Argument(help="Inference endpoint URL."),
    model: str = typer.Option("", help="Optional model name hint."),
    interval: int = typer.Option(30, help="Poll interval in seconds."),
    max_cycles: int = typer.Option(0, help="Maximum cycles; 0 means run until interrupted."),
) -> None:
    """Continuously monitor an endpoint."""
    os.environ["POLL_INTERVAL_SECONDS"] = str(interval)
    config = _load_runtime_config(endpoint)
    from inferguard.agent import InferGuardAgent

    async def _watch() -> None:
        agent = InferGuardAgent(config, model_name=model)
        console.print(f"[green]Watching {endpoint} every {interval}s...[/green]")
        try:
            async for report in agent.watch(max_cycles=max_cycles):
                cycle = report.get("cycle", "?")
                status = report.get("status", "unknown")
                if status == "healthy":
                    kv = report["metrics"].get("kv_cache_usage", "?")
                    console.print(f"[dim]Cycle {cycle}: healthy (KV={kv})[/dim]")
                elif status == "anomaly_detected":
                    console.print(f"\n[red]Cycle {cycle}: anomaly detected[/red]")
                    _print_report(report)
                else:
                    console.print(f"[red]Cycle {cycle}: {report.get('error', 'unknown error')}[/red]")
        finally:
            await agent.shutdown()

    asyncio.run(_watch())


@app.command()
def validate(
    endpoint: str = typer.Argument(help="Inference endpoint URL."),
    export_file: str = typer.Argument(help="Path to ISB-1 export JSON."),
    model: str = typer.Option("", help="Model identifier sent to the endpoint."),
    max_sessions: int = typer.Option(0, help="Cap replay sessions (0=all)."),
    max_concurrency: int = typer.Option(4, help="Max concurrent replay sessions."),
    runtime_stack_id: str = typer.Option("", help="Optional runtime-stack filter."),
) -> None:
    """Run a standalone replay validation against an endpoint."""
    from inferguard.replay_validation import ReplayValidator

    async def _validate() -> dict[str, Any]:
        validator = ReplayValidator(
            export_file=export_file,
            target_endpoint=endpoint,
            model_id=model,
            max_concurrency=max_concurrency,
            max_sessions=max_sessions or None,
            runtime_stack_id=runtime_stack_id or None,
            skip_tokenizer=True,
        )
        result = await validator.run_replay("manual", phase="manual")
        return result.as_dict()

    try:
        result = asyncio.run(_validate())
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(Syntax(json.dumps(result, indent=2), "json", theme="monokai"))


@app.command()
def recall(
    query: str = typer.Argument(help="Search phrase describing a past incident."),
) -> None:
    """Search similar incidents in Upstash Vector memory."""
    vector_url = os.environ.get("UPSTASH_VECTOR_URL", "").strip()
    vector_token = os.environ.get("UPSTASH_VECTOR_TOKEN", "").strip()
    if not (vector_url and vector_token):
        console.print("[red]UPSTASH_VECTOR_URL and UPSTASH_VECTOR_TOKEN are required for recall.[/red]")
        raise typer.Exit(1)

    from inferguard.memory import UpstashVector

    async def _recall() -> list[dict[str, Any]]:
        vector = UpstashVector(vector_url, vector_token)
        return await vector.query(query, top_k=5)

    results = asyncio.run(_recall())
    if not results:
        console.print("[yellow]No similar incidents found.[/yellow]")
        return

    table = Table(title="InferGuard Incident Recall")
    table.add_column("ID")
    table.add_column("Score")
    table.add_column("Engine")
    table.add_column("Severity")
    table.add_column("Fix worked")
    table.add_column("Diagnosis")

    for result in results:
        metadata = result.get("metadata", {})
        table.add_row(
            str(result.get("id", "?")),
            f"{result.get('score', 0):.2f}",
            str(metadata.get("engine", "?")),
            str(metadata.get("severity", "?")),
            str(metadata.get("resolution_effective", "unknown")),
            str(metadata.get("diagnosis", "N/A")),
        )

    console.print(table)


@app.command()
def rlm(
    endpoint: str = typer.Argument(help="Inference endpoint URL to investigate."),
    model: str = typer.Option("", help="Optional model name hint."),
) -> None:
    """Run one proactive RLM investigation cycle and display advisories."""
    config = _load_runtime_config(endpoint)
    from inferguard.agent import InferGuardAgent

    async def _rlm() -> dict[str, Any]:
        agent = InferGuardAgent(config, model_name=model)
        try:
            # We first scrape to capture metrics
            await agent.run_once()
            # Then perform the proactive RLM cycle
            advisories = await agent.proactive_cycle()
            return {
                "status": "success",
                "advisories": [a.as_dict() for a in advisories],
                "model_name": agent.model_name
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}
        finally:
            await agent.shutdown()

    report = asyncio.run(_rlm())
    status = report.get("status", "unknown")
    if status == "success":
        console.print("[green]RLM Active Investigation completed successfully.[/green]")
        advisories = report.get("advisories", [])
        if not advisories:
            console.print("[yellow]No proactive advisories generated.[/yellow]")
            return

        for adv in advisories:
            console.print(Panel(
                f"[bold cyan]Advisory Type:</bold cyan] {adv['advisory_type']}\n"
                f"[bold cyan]Confidence:</bold cyan] {adv['confidence']:.0%}\n"
                f"[bold cyan]Horizon:</bold cyan] {adv['horizon_seconds']}s\n"
                f"[bold cyan]Reason:</bold cyan] {adv['reason']}\n"
                f"[bold cyan]Evidence:</bold cyan]\n" + "\n".join(f"  - {e}" for e in adv['evidence']) + "\n\n"
                f"[bold magenta]Recommended Actions:</bold magenta]\n" + 
                "\n".join(f"  - {act['action_type']}: {act.get('parameters', {})}" for act in adv['recommended_safe_actions']),
                title="InferGuard Proactive RLM Advisory",
                border_style="cyan"
            ))
        return

    console.print(f"[red]Error:[/red] {report.get('error', 'unknown')}")
    raise typer.Exit(1)


@app.command()
def serve(
    endpoint: str = typer.Argument(help="Inference endpoint URL to monitor."),
    model: str = typer.Option("", help="Optional model name hint."),
    transport: str = typer.Option("stdio", help="MCP transport: stdio or streamable-http."),
    port: int = typer.Option(8766, help="Port for streamable-http transport."),
) -> None:
    """Start InferGuard as an optional MCP server."""
    os.environ["TARGET_ENDPOINT"] = endpoint
    if model:
        os.environ["INFERGUARD_MODEL_NAME"] = model

    try:
        from inferguard.mcp_server import create_mcp_server
    except ImportError as exc:
        console.print(
            "[red]MCP support is not installed.[/red] Install with "
            "[bold]pip install '.[mcp]'[/bold] and try again."
        )
        raise typer.Exit(1) from exc

    mcp = create_mcp_server()
    console.print(f"[green]Starting InferGuard MCP server ({transport})...[/green]")
    if transport == "stdio":
        mcp.run(transport="stdio")
        return
    mcp.run(transport=transport, host="127.0.0.1", port=port)


if __name__ == "__main__":
    app()
