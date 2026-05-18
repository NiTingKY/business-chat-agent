from __future__ import annotations

from enum import Enum


class AgentStatus(str, Enum):
    CREATED = "created"
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class AgentLifecycle:
    """Tracks the runtime status of one logical agent."""

    def __init__(self) -> None:
        self._status = AgentStatus.CREATED

    @property
    def status(self) -> AgentStatus:
        return self._status

    def initialize(self) -> None:
        self._status = AgentStatus.INITIALIZING

    def start(self) -> None:
        self._status = AgentStatus.RUNNING

    def pause(self) -> None:
        self._status = AgentStatus.PAUSED

    def stop(self) -> None:
        self._status = AgentStatus.STOPPED

    def fail(self) -> None:
        self._status = AgentStatus.ERROR

