from __future__ import annotations

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical
from textual.widgets import Button, Footer, Header, RichLog, Static

from cerber_launcher.logstream import LogRecord, LogStreamCursor
from cerber_launcher.models import ComponentOverview
from cerber_launcher.runtime import COMPONENT_ORDER, COMPONENT_SPECS, LauncherRuntimeError
from cerber_launcher.supervisor import ERROR_PATTERN, LauncherSupervisor


class ComponentCard(Static):
    def __init__(self, component: str) -> None:
        super().__init__(id=f"card-{component}")
        self.component = component
        self.overview: ComponentOverview | None = None

    def compose(self) -> ComposeResult:
        yield Static("", id=f"title-{self.component}", classes="component-title")
        yield Static("", id=f"meta-{self.component}", classes="component-meta")
        yield Static("", id=f"detail-{self.component}", classes="component-detail")
        with Horizontal(classes="component-actions"):
            yield Button("Логи", id=f"log__{self.component}", variant="primary")
            yield Button("Start", id=f"start__{self.component}", variant="success")
            yield Button("Stop", id=f"stop__{self.component}", variant="error")
            yield Button("Restart", id=f"restart__{self.component}", variant="warning")

    def update_overview(self, overview: ComponentOverview, *, selected_for_logs: bool = False) -> None:
        self.overview = overview
        self.remove_class("running", "stopped", "blocked", "errors", "selected")
        if overview.running:
            self.add_class("running")
        else:
            self.add_class("stopped")
        if not overview.enabled:
            self.add_class("blocked")
        if overview.has_errors:
            self.add_class("errors")
        if selected_for_logs:
            self.add_class("selected")

        status_bits = ["🟢 online" if overview.running else "⚪ offline"]
        if not overview.enabled:
            status_bits.append("нужна настройка")
        if overview.has_errors:
            status_bits.append("есть ошибки")
        if overview.has_logs:
            status_bits.append("пишет логи")

        pid_text = "-" if overview.pid is None else str(overview.pid)
        title = COMPONENT_SPECS[overview.key].label
        subtitle = f"{overview.kind.upper()} · PID {pid_text}"

        self.query_one(f"#title-{self.component}", Static).update(f"{title}\n{subtitle}")
        self.query_one(f"#meta-{self.component}", Static).update(" • ".join(status_bits))
        detail = overview.detail or "Без дополнительных деталей"
        if overview.command:
            detail = f"{detail}\nКоманда: {overview.command}"
        self.query_one(f"#detail-{self.component}", Static).update(detail)


class LauncherDashboardApp(App[None]):
    CSS = """
    Screen {
        background: #0d1117;
        color: #f0f6fc;
    }

    #workspace {
        layout: grid;
        grid-size: 2 1;
        grid-columns: 7fr 5fr;
        padding: 1 2;
        height: 1fr;
    }

    #left-pane {
        margin-right: 1;
        height: 1fr;
    }

    #right-pane {
        border: round #3b82f6;
        background: #111827;
        padding: 1;
        height: 1fr;
    }

    #hero {
        border: round #3b82f6;
        background: #111827;
        padding: 1 2;
        margin-bottom: 1;
        height: auto;
    }

    #summary {
        border: round #10b981;
        background: #0f172a;
        padding: 1 2;
        margin-bottom: 1;
        height: auto;
    }

    #cards-grid {
        grid-size: 2 2;
        grid-columns: 1fr 1fr;
        grid-rows: auto auto;
        grid-gutter: 1 1;
        height: auto;
        margin-bottom: 1;
    }

    ComponentCard {
        border: round #334155;
        background: #0f172a;
        padding: 1;
        min-height: 15;
    }

    ComponentCard.running {
        border: round #10b981;
    }

    ComponentCard.errors {
        border: round #f59e0b;
    }

    ComponentCard.blocked {
        border: round #ef4444;
    }

    ComponentCard.selected {
        tint: #1d4ed833;
    }

    .component-title {
        text-style: bold;
        color: #e2e8f0;
        margin-bottom: 1;
    }

    .component-meta {
        color: #93c5fd;
        margin-bottom: 1;
    }

    .component-detail {
        color: #cbd5e1;
        height: 5;
        margin-bottom: 1;
    }

    .component-actions {
        height: auto;
    }

    .component-actions Button {
        width: 1fr;
        margin-right: 1;
    }

    #global-actions {
        border: round #334155;
        background: #111827;
        padding: 1;
        height: auto;
    }

    #global-actions Button {
        width: 1fr;
        margin-right: 1;
    }

    #log-title {
        text-style: bold;
        color: #93c5fd;
        margin-bottom: 1;
    }

    #log-subtitle {
        color: #94a3b8;
        margin-bottom: 1;
        height: auto;
    }

    #log-view {
        border: round #334155;
        background: #020617;
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Выход"),
        Binding("r", "refresh_dashboard", "Обновить"),
        Binding("s", "start_defaults", "Старт"),
        Binding("x", "stop_all", "Стоп всё"),
        Binding("ctrl+l", "focus_logs", "Логи"),
    ]

    def __init__(self, supervisor: LauncherSupervisor | None = None) -> None:
        super().__init__()
        self.supervisor = supervisor or LauncherSupervisor()
        self.selected_log_target = "shop"
        self._log_cursor: LogStreamCursor | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="workspace"):
            with Vertical(id="left-pane"):
                yield Static(
                    "🚀 CERBER Launcher Dashboard\nСовременная панель управления компонентами shop / admin / ceer / tunnel с живыми логами.",
                    id="hero",
                )
                yield Static("", id="summary")
                with Grid(id="cards-grid"):
                    for component in COMPONENT_ORDER:
                        yield ComponentCard(component)
                with Horizontal(id="global-actions"):
                    yield Button("Старт по умолчанию", id="start-defaults", variant="success")
                    yield Button("Стоп всё", id="stop-all", variant="error")
                    yield Button("Рестарт всё", id="restart-all", variant="warning")
                    yield Button("Логи launcher", id="log__launcher", variant="primary")
            with Vertical(id="right-pane"):
                yield Static("Живой поток логов", id="log-title")
                yield Static("", id="log-subtitle")
                yield RichLog(id="log-view", wrap=True, highlight=True, markup=False, auto_scroll=True)
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_dashboard()
        self._select_log_target(self.selected_log_target)
        self.set_interval(1.5, self.refresh_dashboard)
        self.set_interval(0.6, self._poll_logs)

    def action_refresh_dashboard(self) -> None:
        self.refresh_dashboard()
        self.notify("Статусы обновлены")

    def action_start_defaults(self) -> None:
        targets = self.supervisor.default_targets()
        self._run_action("start", targets, "Стандартный набор")

    def action_stop_all(self) -> None:
        self._run_action("stop", list(COMPONENT_ORDER), "Все компоненты")

    def action_focus_logs(self) -> None:
        self.query_one("#log-view", RichLog).focus()

    def refresh_dashboard(self) -> None:
        overviews = self.supervisor.collect_component_overviews(list(COMPONENT_ORDER))
        summary = self.supervisor.build_summary(list(COMPONENT_ORDER))
        summary_lines = [
            f"Всего компонентов: {summary.total_components}",
            f"Готово к запуску: {summary.enabled_components}",
            f"Онлайн сейчас: {summary.running_components}",
            f"С живыми логами: {summary.components_with_logs}",
            f"С ошибками: {summary.components_with_errors}",
            f"Активный лог-поток: {self.selected_log_target}",
        ]
        self.query_one("#summary", Static).update("\n".join(summary_lines))

        for overview in overviews:
            card = self.query_one(f"#card-{overview.key}", ComponentCard)
            card.update_overview(overview, selected_for_logs=overview.key == self.selected_log_target)

        self._update_log_subtitle()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "start-defaults":
            self.action_start_defaults()
            return
        if button_id == "stop-all":
            self.action_stop_all()
            return
        if button_id == "restart-all":
            self._run_action("restart", list(COMPONENT_ORDER), "Все компоненты")
            return

        action, _, component = button_id.partition("__")
        if not component:
            return

        if action == "log":
            self._select_log_target(component)
            self.notify(f"Логи переключены на {component}")
            return

        if action in {"start", "stop", "restart"}:
            self._run_action(action, [component], COMPONENT_SPECS[component].label)

    def _run_action(self, action: str, components: list[str], target_name: str) -> None:
        try:
            if action == "start":
                statuses = self.supervisor.start_components(components)
            elif action == "stop":
                statuses = self.supervisor.stop_components(components)
            elif action == "restart":
                statuses = self.supervisor.restart_components(components)
            else:
                raise LauncherRuntimeError(f"Неизвестное действие: {action}")
        except LauncherRuntimeError as error:
            self.notify(str(error), severity="error")
            return

        details = "; ".join(f"{status.label}: {status.detail}" for status in statuses)
        self.notify(f"{target_name}: {details}")
        self.refresh_dashboard()
        if self.selected_log_target in components:
            self._select_log_target(self.selected_log_target)

    def _select_log_target(self, target: str) -> None:
        self.selected_log_target = target
        entries = self.supervisor.log_paths_for_target(target)
        self._log_cursor = LogStreamCursor(entries)
        log_view = self.query_one("#log-view", RichLog)
        log_view.clear()
        for record in self._log_cursor.snapshot(tail_lines=80):
            self._append_record(record)
        self.refresh_dashboard()

    def _update_log_subtitle(self) -> None:
        entries = self.supervisor.log_paths_for_target(self.selected_log_target)
        lines = [f"Источник: {self.selected_log_target}"]
        for label, path in entries:
            lines.append(f"• {label}: {path.name}")
        self.query_one("#log-subtitle", Static).update("\n".join(lines))

    def _poll_logs(self) -> None:
        if self._log_cursor is None:
            return
        for record in self._log_cursor.poll():
            self._append_record(record)

    def _append_record(self, record: LogRecord) -> None:
        line = Text()
        line.append(f"[{record.source}] ", style="bold cyan")
        style = "bold red" if ERROR_PATTERN.search(record.line) else "white"
        line.append(record.line or " ", style=style)
        self.query_one("#log-view", RichLog).write(line)
