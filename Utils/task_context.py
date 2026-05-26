from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Dict, Optional

_current_task: ContextVar[Optional[Dict[str, Any]]] = ContextVar("current_task", default=None)


def set_current_task(task: Optional[Dict[str, Any]]) -> None:
    _current_task.set(task)


def get_current_task() -> Optional[Dict[str, Any]]:
    return _current_task.get()


def clear_current_task() -> None:
    _current_task.set(None)
