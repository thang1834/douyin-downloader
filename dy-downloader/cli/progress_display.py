from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.table import Table
from rich.panel import Panel

console = Console()


class ProgressDisplay:
    def __init__(self):
        self.console = console

    def show_banner(self):
        banner = """
╔══════════════════════════════════════════╗
║     Douyin Downloader v1.0.0            ║
║     Công cụ tải xuống hàng loạt Douyin  ║
╚══════════════════════════════════════════╝
        """
        self.console.print(banner, style="bold cyan")

    def create_progress(self) -> Progress:
        return Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=self.console
        )

    def show_result(self, result):
        table = Table(title="Tóm tắt tải xuống", show_header=True, header_style="bold magenta")
        table.add_column("Chỉ số", style="cyan")
        table.add_column("Số lượng", justify="right", style="green")

        table.add_row("Tổng", str(result.total))
        table.add_row("Thành công", str(result.success))
        table.add_row("Thất bại", str(result.failed))
        table.add_row("Bỏ qua", str(result.skipped))

        if result.total > 0:
            success_rate = (result.success / result.total) * 100
            table.add_row("Tỷ lệ thành công", f"{success_rate:.1f}%")

        self.console.print(table)

    def print_info(self, message: str):
        self.console.print(f"[blue]ℹ[/blue] {message}")

    def print_success(self, message: str):
        self.console.print(f"[green]✓[/green] {message}")

    def print_warning(self, message: str):
        self.console.print(f"[yellow]⚠[/yellow] {message}")

    def print_error(self, message: str):
        self.console.print(f"[red]✗[/red] {message}")
