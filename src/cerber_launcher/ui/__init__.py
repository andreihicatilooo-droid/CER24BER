from __future__ import annotations


def launch_dashboard() -> int:
    from cerber_launcher.ui.app import LauncherDashboardApp

    app = LauncherDashboardApp()
    app.run()
    return 0
