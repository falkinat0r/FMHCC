"""ActionJob-Status-State-Machine (R1, frozen Semantik).

Einziges Moegliches Ziel aus jedem Zustand; Terminal-Zustaende sind
endgueltig (keine Weiterrueckkehr). Diese Definition ist die
verbindliche Basis fuer Tests und die spaetere API (Agent 3).
"""

from __future__ import annotations

from app.models.action_jobs import JobStatus

TERMINAL_STATUSES = frozenset({JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED})

ALLOWED_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.PENDING: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED}),
    JobStatus.RUNNING: frozenset({JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}),
    JobStatus.SUCCEEDED: frozenset(),
    JobStatus.FAILED: frozenset(),
    JobStatus.CANCELLED: frozenset(),
}
