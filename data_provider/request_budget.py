"""Small, file-backed daily request budgets for low-quota data providers.

The budget is deliberately provider-specific and lives outside the normal
analysis cache.  GitHub Actions can restore/save that directory between the
daily, weekly and monthly jobs, while local runs can use the same guard.
"""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional
from zoneinfo import ZoneInfo

try:  # pragma: no cover - Windows fallback is exercised by the no-op path.
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None


@dataclass(frozen=True)
class BudgetReservation:
    allowed: bool
    used: int
    remaining: int
    bucket: str


class DailyRequestBudget:
    """Atomically reserve requests up to a per-calendar-day limit."""

    def __init__(
        self,
        path: str | Path,
        daily_limit: int = 25,
        timezone_name: str = "UTC",
    ) -> None:
        self.path = Path(path)
        self.daily_limit = max(0, int(daily_limit))
        try:
            self._timezone = ZoneInfo(timezone_name)
            self.timezone_name = timezone_name
        except Exception:
            self._timezone = timezone.utc
            self.timezone_name = "UTC"

    @classmethod
    def from_env(cls) -> "DailyRequestBudget":
        def _int(name: str, default: int) -> int:
            try:
                return int(os.getenv(name, str(default)).strip())
            except (TypeError, ValueError):
                return default

        return cls(
            os.getenv("ALPHAVANTAGE_BUDGET_FILE", "data/provider_budget/alphavantage.json"),
            daily_limit=_int("ALPHAVANTAGE_MAX_REQUESTS_PER_DAY", 25),
            timezone_name=os.getenv("ALPHAVANTAGE_BUDGET_TIMEZONE", "UTC").strip() or "UTC",
        )

    def _bucket(self, now: Optional[datetime] = None) -> str:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        return current.astimezone(self._timezone).date().isoformat()

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _read_state(self, bucket: str) -> tuple[str, int]:
        if not self.path.exists():
            return bucket, 0
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if payload.get("bucket") != bucket:
                return bucket, 0
            used = int(payload.get("used", 0))
            if used < 0 or used > self.daily_limit:
                raise ValueError("invalid used count")
            return bucket, used
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            # A corrupt counter must fail closed; silently resetting it could
            # exceed Alpha Vantage's provider-side daily quota.
            return bucket, self.daily_limit

    def _write_state(self, bucket: str, used: int) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=".alphavantage-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "provider": "alphavantage",
                        "bucket": bucket,
                        "used": used,
                        "limit": self.daily_limit,
                        "timezone": self.timezone_name,
                    },
                    handle,
                    ensure_ascii=False,
                    sort_keys=True,
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def try_reserve(self, count: int = 1, *, now: Optional[datetime] = None) -> BudgetReservation:
        count = int(count)
        bucket = self._bucket(now)
        if count <= 0:
            return BudgetReservation(True, 0, self.daily_limit, bucket)
        if count > self.daily_limit:
            return BudgetReservation(False, self.daily_limit, 0, bucket)

        with self._locked():
            bucket, used = self._read_state(bucket)
            if used + count > self.daily_limit:
                return BudgetReservation(False, used, self.daily_limit - used, bucket)
            used += count
            self._write_state(bucket, used)
            return BudgetReservation(True, used, self.daily_limit - used, bucket)


