"""CLI entrypoint for ReviewSentinel."""

import sys
import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from dotenv import load_dotenv
import logging
import os

load_dotenv()

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

console = Console()


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


@click.group()
@click.option("--log-level", default="INFO", help="Logging verbosity.")
@click.pass_context
def main(ctx: click.Context, log_level: str) -> None:
    """ReviewSentinel — AI-powered GitHub PR Code Review Agent."""
    ctx.ensure_object(dict)
    ctx.obj["log_level"] = log_level
    setup_logging(log_level)


@main.command()
@click.option("--pr", required=True, type=int, help="Pull request number.")
@click.option("--repo", required=True, help="Repository in owner/repo format.")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Parse diff and run analysis but do NOT post any comments to GitHub.",
)
@click.option(
    "--cost-estimate",
    is_flag=True,
    default=False,
    help="Print estimated token cost before running.",
)
@click.option(
    "--output",
    type=click.Choice(["github", "json", "markdown"]),
    default="github",
    help="Where/how to output the review.",
)
@click.pass_context
def run(
    ctx: click.Context,
    pr: int,
    repo: str,
    dry_run: bool,
    cost_estimate: bool,
    output: str,
) -> None:
    """Run the full code review pipeline on a pull request."""
    from review_agent.pipeline import ReviewPipeline

    dry_run = dry_run or os.getenv("DRY_RUN", "false").lower() == "true"

    console.print(
        Panel.fit(
            f"[bold cyan]ReviewSentinel[/bold cyan] v0.1.0\n"
            f"[dim]Repository:[/dim] {repo}  [dim]PR:[/dim] #{pr}  "
            f"[dim]Mode:[/dim] {'dry-run' if dry_run else 'live'}",
            border_style="cyan",
        )
    )

    pipeline = ReviewPipeline(
        repo=repo,
        pr_number=pr,
        dry_run=dry_run,
        cost_estimate=cost_estimate,
        output_mode=output,
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Running review pipeline…", total=None)
        result = pipeline.run()
        progress.update(task, description="[green]Review complete!")

    if result.get("error"):
        console.print(f"[bold red]Error:[/bold red] {result['error']}")
        sys.exit(1)

    console.print(f"\n[bold green]✓[/bold green] Review posted with "
                  f"[bold]{result.get('total_findings', 0)}[/bold] findings.")

    if cost_estimate:
        console.print(
            f"[dim]Estimated cost: ${result.get('estimated_cost_usd', 0):.4f} USD[/dim]"
        )


@main.command()
@click.option("--repo-path", default=".", help="Local path to the repository to index.")
@click.option("--chroma-path", default=None, help="Override ChromaDB path.")
@click.pass_context
def index(ctx: click.Context, repo_path: str, chroma_path: str) -> None:
    """Index a repository into ChromaDB for RAG context retrieval."""
    from review_agent.indexing.embedder import RepositoryIndexer

    console.print(f"[cyan]Indexing repository at:[/cyan] {repo_path}")
    indexer = RepositoryIndexer(repo_path=repo_path, chroma_path=chroma_path)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Indexing files…", total=None)
        stats = indexer.index_all()
        progress.update(task, description="[green]Indexing complete!")

    console.print(
        f"[green]✓[/green] Indexed [bold]{stats['files']}[/bold] files "
        f"([bold]{stats['chunks']}[/bold] chunks)."
    )


if __name__ == "__main__":
    main()
