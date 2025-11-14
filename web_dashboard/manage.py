#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
from pathlib import Path
import importlib.util


def _load_config_into_sys_modules():
    """Load repository config.py as module 'config' without changing sys.path."""
    repo_root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("config", str(repo_root / "config.py"))
    cfg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cfg)
    sys.modules["config"] = cfg


def main():
    """Run administrative tasks."""
    # ensure config is available as a module before Django loads settings
    try:
        _load_config_into_sys_modules()
    except Exception:
        # If loading fails, Django's settings may still try to import config (they currently modify sys.path),
        # so we don't hard-fail here. But prefer to have config available.
        pass

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'web_dashboard.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
