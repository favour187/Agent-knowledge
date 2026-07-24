"""
Training Monitoring & Logging

Real-time monitoring for adapter training runs with progress tracking,
resource monitoring, and result reporting. Designed for production
fine-tuning pipelines where visibility into adapter training is critical.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class TrainingMonitor:
    """Monitor a training run."""
    run_id: str
    adapter_path: Optional[str] = None
    start_time: Optional[float] = None
    checkpoints: list[str] = field(default_factory=list)
    metrics_history: list[dict[str, Any]] = field(default_factory=list)

    def start(self, adapter_path: Optional[str] = None) -> None:
        self.adapter_path = adapter_path
        self.start_time = time.time()
        logger.info("monitoring_started", run_id=self.run_id, adapter_path=adapter_path)

    def log_checkpoint(self, path: str, step: int, epoch: float, loss: float) -> None:
        self.checkpoints.append(path)
        logger.info("checkpoint_created", path=path, step=step, epoch=epoch, loss=loss, run_id=self.run_id)

    def log_metrics(self, step: int, metrics: dict[str, float]) -> None:
        entry = {
            "step": step,
            "timestamp": datetime.utcnow().isoformat(),
            "metrics": metrics,
        }
        self.metrics_history.append(entry)
        logger.info("metrics_logged", step=step, metrics=metrics, run_id=self.run_id)

    def get_duration(self) -> float:
        if self.start_time is None:
            return 0.0
        return time.time() - self.start_time

    def to_summary(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "adapter_path": self.adapter_path,
            "duration_seconds": self.get_duration(),
            "checkpoints_created": len(self.checkpoints),
            "metrics_entries": len(self.metrics_history),
            "latest_metrics": self.metrics_history[-1]["metrics"] if self.metrics_history else {},
        }
