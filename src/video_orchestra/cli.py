from __future__ import annotations

import json
import secrets
import sys
from pathlib import Path
from typing import Any

import httpx
import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from video_orchestra.comfy import ComfyClient
from video_orchestra.config import Settings
from video_orchestra.errors import VideoOrchestraError
from video_orchestra.jobs import JobRun, utc_now
from video_orchestra.workflow import WorkflowAdapter, is_special_node, load_api_workflow

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Локальный запуск Wan 2.2 workflow через ComfyUI.",
)
console = Console()


def _settings_or_exit() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        console.print(f"[bold red]Ошибка настроек:[/bold red] {exc}")
        raise typer.Exit(2) from exc


@app.command()
def doctor() -> None:
    """Проверить Python, ComfyUI и API workflow."""
    settings = _settings_or_exit()
    checks: list[tuple[str, bool, str]] = []

    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    python_ok = sys.version_info[:2] == (3, 11)
    checks.append(("Python 3.11", python_ok, version))

    try:
        response = httpx.get(settings.comfy_url, timeout=5, follow_redirects=True)
        comfy_ok = response.status_code < 500
        comfy_detail = f"HTTP {response.status_code} — {settings.comfy_url}"
    except httpx.HTTPError as exc:
        comfy_ok = False
        comfy_detail = f"недоступен: {exc}"
    checks.append(("ComfyUI", comfy_ok, comfy_detail))

    workflow_path = settings.comfy_workflow
    exists = workflow_path.is_file()
    checks.append(("Файл workflow", exists, str(workflow_path)))

    workflow = None
    if exists:
        try:
            workflow = load_api_workflow(workflow_path)
            checks.append(("API-формат workflow", True, f"узлов: {len(workflow)}"))
        except VideoOrchestraError as exc:
            checks.append(("API-формат workflow", False, str(exc)))
    else:
        checks.append(("API-формат workflow", False, "проверка невозможна: файл не найден"))

    if workflow is not None:
        try:
            required = WorkflowAdapter(workflow).find_required_nodes()
            detail = ", ".join(
                f"{node.class_type}:{node.node_id}"
                for node in (
                    required.positive,
                    required.negative,
                    required.sampler,
                    required.latent,
                    required.create_video,
                    required.save_video,
                )
            )
            checks.append(("Обязательные узлы", True, detail))
        except VideoOrchestraError as exc:
            checks.append(("Обязательные узлы", False, str(exc)))
    else:
        checks.append(("Обязательные узлы", False, "проверка невозможна"))

    table = Table(title="Диагностика ai-video-orchestra")
    table.add_column("Результат", no_wrap=True)
    table.add_column("Проверка")
    table.add_column("Подробности", overflow="fold")
    for label, ok, detail in checks:
        table.add_row("[green]OK[/green]" if ok else "[red]FAIL[/red]", label, detail)
    console.print(table)
    if not all(ok for _, ok, _ in checks):
        raise typer.Exit(1)


@app.command("inspect-workflow")
def inspect_workflow(
    workflow_path: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
) -> None:
    """Показать узлы ComfyUI API workflow без предположений об их ID."""
    try:
        adapter = WorkflowAdapter.from_file(workflow_path)
    except VideoOrchestraError as exc:
        console.print(f"[bold red]Ошибка workflow:[/bold red] {exc}")
        raise typer.Exit(1) from exc

    table = Table(title=f"Workflow: {workflow_path}", show_lines=True)
    table.add_column("node_id", style="cyan", no_wrap=True)
    table.add_column("class_type", no_wrap=True)
    table.add_column("_meta.title")
    table.add_column("inputs")
    table.add_column("текущие значения", overflow="fold")
    for node in adapter.nodes():
        style = "bold yellow" if is_special_node(node) else None
        values = json.dumps(node.inputs, ensure_ascii=False, default=str)
        table.add_row(
            node.node_id,
            node.class_type,
            node.title or "—",
            ", ".join(node.inputs) or "—",
            values,
            style=style,
        )
    console.print(table)
    console.print("[yellow]Жёлтым[/yellow] выделены узлы, используемые генератором.")


def _positive_int(value: int, name: str) -> None:
    if value <= 0:
        raise typer.BadParameter(f"{name} должен быть больше нуля")


@app.command()
def generate(
    prompt: str = typer.Option(..., "--prompt", help="Positive prompt"),
    negative: str = typer.Option("", "--negative", help="Negative prompt"),
    width: int = typer.Option(480, "--width"),
    height: int = typer.Option(832, "--height"),
    frames: int = typer.Option(81, "--frames"),
    fps: float = typer.Option(16, "--fps"),
    seed: int | None = typer.Option(None, "--seed"),
    steps: int = typer.Option(20, "--steps"),
    cfg: float = typer.Option(5, "--cfg"),
    output: Path | None = typer.Option(
        None,
        "--output",
        file_okay=False,
        help="Каталог задач (по умолчанию RUNS_DIR или runs)",
    ),
) -> None:
    """Запустить workflow, дождаться завершения и сохранить scene.mp4."""
    integer_values = ((width, "width"), (height, "height"), (frames, "frames"), (steps, "steps"))
    for value, name in integer_values:
        _positive_int(value, name)
    if fps <= 0 or cfg <= 0:
        raise typer.BadParameter("fps и cfg должны быть больше нуля")
    if seed is not None and seed < 0:
        raise typer.BadParameter("seed не может быть отрицательным")

    settings = _settings_or_exit()
    actual_seed = seed if seed is not None else secrets.randbits(63)
    runs_dir = output if output is not None else settings.runs_dir
    try:
        job = JobRun(runs_dir)
    except OSError as exc:
        console.print(f"[bold red]Не удалось создать каталог задачи:[/bold red] {exc}")
        raise typer.Exit(1) from exc

    request: dict[str, Any] = {
        "job_id": job.job_id,
        "created_at": utc_now(),
        "workflow": str(settings.comfy_workflow),
        "prompt": prompt,
        "negative": negative,
        "width": width,
        "height": height,
        "frames": frames,
        "fps": fps,
        "seed": actual_seed,
        "steps": steps,
        "cfg": cfg,
    }
    job.write_request(request)
    console.print(f"Задача [cyan]{job.job_id}[/cyan] создана: {job.directory}")

    stage = "load_workflow"
    try:
        adapter = WorkflowAdapter.from_file(settings.comfy_workflow)
        workflow = adapter.apply(
            prompt=prompt,
            negative=negative,
            width=width,
            height=height,
            frames=frames,
            fps=fps,
            seed=actual_seed,
            steps=steps,
            cfg=cfg,
            filename_prefix=f"ai-video-orchestra_{job.job_id}_scene",
        )
        job.write_workflow(workflow)

        stage = "submit"
        with ComfyClient(settings.comfy_url, settings.comfy_timeout_sec) as client:
            prompt_id = client.queue_prompt(workflow)
            job.prompt_id = prompt_id
            job.write_status("submitted", stage=stage)
            console.print(f"Workflow принят ComfyUI, prompt_id: [cyan]{prompt_id}[/cyan]")

            stage = "generating"
            job.write_status("generating", stage=stage)
            client.wait_for_completion(prompt_id)

            stage = "history"
            history = client.get_history(prompt_id)
            remote_output = client.find_output(history)

            stage = "download"
            client.download_output(remote_output, job.video_path)

        stage = "completed"
        job.write_status(
            "completed",
            stage=stage,
            output=str(job.video_path),
            source_file=remote_output["filename"],
        )
        console.print(f"[bold green]Готово:[/bold green] {job.video_path}")
    except Exception as exc:
        job.fail(stage=stage, error=exc)
        console.print(f"[bold red]Ошибка на этапе {stage}:[/bold red] {exc}")
        console.print(f"Подробности: {job.directory / 'status.json'} и {job.directory / 'run.log'}")
        raise typer.Exit(1) from exc
