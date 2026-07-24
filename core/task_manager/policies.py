"""
Execution Policies

Retry, timeout, and execution policies for task management.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

import structlog

logger = structlog.get_logger(__name__)


class RetryStrategy(str, Enum):
    """Retry strategies."""
    FIXED = "fixed"                    # Fixed delay between retries
    LINEAR = "linear"                  # Linear backoff
    EXPONENTIAL = "exponential"       # Exponential backoff
    FIBONACCI = "fibonacci"            # Fibonacci backoff
    IMMEDIATE = "immediate"           # No delay


@dataclass
class RetryPolicy:
    """
    Policy for retrying failed tasks.

    Attributes:
        strategy: Backoff strategy to use
        max_attempts: Maximum number of retry attempts
        base_delay: Base delay in seconds
        max_delay: Maximum delay cap
        jitter: Add randomness to delay (0.0-1.0)
        retryable_errors: Error types that should be retried
        fatal_errors: Error types that should not be retried
    """
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    jitter: float = 0.1  # 10% randomness
    retryable_errors: tuple[str, ...] = ("timeout", "connection", "rate_limit")
    fatal_errors: tuple[str, ...] = ("auth", "permission", "validation")
    on_retry: Optional[Callable[[int, Exception], None]] = None

    def calculate_delay(self, attempt: int) -> float:
        """
        Calculate delay for given attempt number.

        Args:
            attempt: Current attempt number (1-indexed)

        Returns:
            Delay in seconds
        """
        if self.strategy == RetryStrategy.IMMEDIATE:
            delay = 0.0
        elif self.strategy == RetryStrategy.FIXED:
            delay = self.base_delay
        elif self.strategy == RetryStrategy.LINEAR:
            delay = self.base_delay * attempt
        elif self.strategy == RetryStrategy.EXPONENTIAL:
            delay = self.base_delay * (2 ** (attempt - 1))
        elif self.strategy == RetryStrategy.FIBONACCI:
            # Fibonacci sequence for delays
            a, b = 1, 1
            for _ in range(attempt - 1):
                a, b = b, a + b
            delay = self.base_delay * a
        else:
            delay = self.base_delay

        # Apply max delay cap
        delay = min(delay, self.max_delay)

        # Apply jitter
        if self.jitter > 0:
            import random
            jitter_range = delay * self.jitter
            delay += random.uniform(-jitter_range, jitter_range)

        return max(0, delay)

    def should_retry(self, error: Exception, attempt: int) -> bool:
        """
        Determine if an error should be retried.

        Args:
            error: The exception that occurred
            attempt: Current attempt number

        Returns:
            True if should retry
        """
        if attempt >= self.max_attempts:
            return False

        error_type = type(error).__name__.lower()
        error_message = str(error).lower()

        # Check fatal errors
        for fatal in self.fatal_errors:
            if fatal in error_type or fatal in error_message:
                logger.info(
                    "retry_aborted_fatal",
                    error_type=error_type,
                    attempt=attempt,
                )
                return False

        # Check retryable errors
        for retryable in self.retryable_errors:
            if retryable in error_type or retryable in error_message:
                return True

        # Default: retry server errors
        return True

    def notify_retry(self, attempt: int, error: Exception) -> None:
        """Notify about retry attempt."""
        if self.on_retry:
            self.on_retry(attempt, error)


@dataclass
class TimeoutPolicy:
    """
    Policy for task timeout handling.

    Attributes:
        default_timeout: Default timeout in seconds
        enable_soft_timeout: Enable soft timeout warnings
        soft_timeout_fraction: Fraction of timeout for soft timeout
        timeout_action: Action to take on timeout
    """
    default_timeout: Optional[float] = None
    enable_soft_timeout: bool = True
    soft_timeout_fraction: float = 0.8
    timeout_action: str = "cancel"  # cancel, extend, escalate


@dataclass
class ExecutionPolicy:
    """
    Combined execution policy for task management.

    Attributes:
        retry: Retry policy
        timeout: Timeout policy
        concurrency: Maximum concurrent executions
        priority_boost_on_retry: Increase priority on retry
        abort_on_first_failure: Stop execution chain on failure
    """
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    timeout: TimeoutPolicy = field(default_factory=TimeoutPolicy)
    concurrency: int = 10
    priority_boost_on_retry: bool = True
    abort_on_first_failure: bool = False

    @classmethod
    def default(cls) -> ExecutionPolicy:
        """Get default execution policy."""
        return cls()

    @classmethod
    def aggressive(cls) -> ExecutionPolicy:
        """Get aggressive policy with many retries."""
        return cls(
            retry=RetryPolicy(
                strategy=RetryStrategy.EXPONENTIAL,
                max_attempts=5,
                base_delay=0.5,
            ),
            concurrency=20,
        )

    @classmethod
    def conservative(cls) -> ExecutionPolicy:
        """Get conservative policy with few retries."""
        return cls(
            retry=RetryPolicy(
                strategy=RetryStrategy.LINEAR,
                max_attempts=2,
                base_delay=2.0,
            ),
            timeout=TimeoutPolicy(default_timeout=30.0),
            concurrency=5,
        )

    @classmethod
    def fast(cls) -> ExecutionPolicy:
        """Get fast policy with no retries."""
        return cls(
            retry=RetryPolicy(max_attempts=1),
            timeout=TimeoutPolicy(default_timeout=10.0),
            concurrency=50,
        )
