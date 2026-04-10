import json
import logging
import os
import signal
import socket
import subprocess
import time
import uuid
from dataclasses import dataclass
from typing import List, Optional

from redis import Redis


logging.basicConfig(
    level=os.getenv("WORKER_POOL_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [worker-pool] %(levelname)s: %(message)s",
)
logger = logging.getLogger("worker_pool")


REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
DEFAULT_DESIRED = int(os.getenv("RQ_WORKER_DEFAULT_COUNT", "1"))
MIN_WORKERS = int(os.getenv("RQ_WORKER_MIN_COUNT", "1"))
MAX_WORKERS = int(os.getenv("RQ_WORKER_MAX_COUNT", "16"))
POLL_SECONDS = float(os.getenv("RQ_WORKER_POOL_POLL_SECONDS", "2"))

DESIRED_KEY = os.getenv("RQ_WORKER_DESIRED_KEY", "rq:workers:desired_count")
MANAGER_HEARTBEAT_KEY = os.getenv("RQ_WORKER_MANAGER_HEARTBEAT_KEY", "rq:workers:manager:heartbeat")
MANAGER_HEARTBEAT_TTL = int(os.getenv("RQ_WORKER_MANAGER_HEARTBEAT_TTL_SECONDS", "15"))
QUEUE_NAMES = [item.strip() for item in os.getenv("RQ_QUEUE_NAMES", "default").split(",") if item.strip()]
BASE_NAME_PREFIX = os.getenv("RQ_WORKER_NAME_PREFIX", socket.gethostname())
# Unique per manager process so stale Redis worker entries from prior runs
# do not block startup with "There exists an active worker named ... already".
NAME_SUFFIX = os.getenv("RQ_WORKER_NAME_SUFFIX", uuid.uuid4().hex[:8])
NAME_PREFIX = f"{BASE_NAME_PREFIX}-{NAME_SUFFIX}"


@dataclass
class ManagedProcess:
    role: str
    index: Optional[int]
    name: str
    process: subprocess.Popen


class WorkerPoolManager:
    def __init__(self) -> None:
        self.redis = Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        self.processes: List[ManagedProcess] = []
        self._running = True

    def _clamp(self, value: int) -> int:
        return max(MIN_WORKERS, min(MAX_WORKERS, value))

    def _default_desired(self) -> int:
        return self._clamp(DEFAULT_DESIRED)

    def _read_desired_count(self) -> int:
        raw = self.redis.get(DESIRED_KEY)
        if raw is None:
            desired = self._default_desired()
            self.redis.set(DESIRED_KEY, str(desired))
            return desired

        try:
            parsed = int(str(raw).strip())
        except Exception:
            parsed = self._default_desired()

        clamped = self._clamp(parsed)
        if clamped != parsed:
            self.redis.set(DESIRED_KEY, str(clamped))
        return clamped

    def _spawn(self, role: str, index: Optional[int]) -> None:
        if role == "scheduler":
            name = f"{NAME_PREFIX}-rq-scheduler"
            cmd = ["rq", "worker", *QUEUE_NAMES, "--with-scheduler", "--name", name]
        else:
            idx = int(index or 0)
            name = f"{NAME_PREFIX}-rq-worker-{idx}"
            cmd = ["rq", "worker", *QUEUE_NAMES, "--name", name]

        logger.info("Starting %s process: %s", role, " ".join(cmd))
        proc = subprocess.Popen(cmd)
        self.processes.append(ManagedProcess(role=role, index=index, name=name, process=proc))

    def _alive(self, managed: ManagedProcess) -> bool:
        return managed.process.poll() is None

    def _cleanup_dead(self) -> None:
        alive: List[ManagedProcess] = []
        for managed in self.processes:
            if self._alive(managed):
                alive.append(managed)
            else:
                logger.warning("%s exited with code %s", managed.name, managed.process.returncode)
        self.processes = alive

    def _find_scheduler(self) -> Optional[ManagedProcess]:
        for managed in self.processes:
            if managed.role == "scheduler" and self._alive(managed):
                return managed
        return None

    def _regular_workers(self) -> List[ManagedProcess]:
        return [managed for managed in self.processes if managed.role == "worker" and self._alive(managed)]

    def _terminate(self, managed: ManagedProcess) -> None:
        if not self._alive(managed):
            return
        logger.info("Stopping %s", managed.name)
        managed.process.terminate()
        try:
            managed.process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            logger.warning("Force killing %s", managed.name)
            managed.process.kill()
            managed.process.wait(timeout=4)

    def _reconcile(self, desired_count: int) -> None:
        self._cleanup_dead()

        if self._find_scheduler() is None:
            self._spawn(role="scheduler", index=None)

        target_regular = max(0, desired_count - 1)
        regular = sorted(self._regular_workers(), key=lambda item: int(item.index or 0))

        while len(regular) < target_regular:
            existing_indexes = {int(item.index or 0) for item in regular}
            next_idx = 1
            while next_idx in existing_indexes:
                next_idx += 1
            self._spawn(role="worker", index=next_idx)
            self._cleanup_dead()
            regular = sorted(self._regular_workers(), key=lambda item: int(item.index or 0))

        while len(regular) > target_regular:
            victim = regular.pop()
            self._terminate(victim)
            self._cleanup_dead()

    def _publish_heartbeat(self, desired_count: int) -> None:
        active = sum(1 for managed in self.processes if self._alive(managed))
        payload = {
            "desired_count": desired_count,
            "active_processes": active,
            "updated_at": int(time.time()),
        }
        self.redis.setex(MANAGER_HEARTBEAT_KEY, MANAGER_HEARTBEAT_TTL, json.dumps(payload))

    def stop(self) -> None:
        self._running = False
        for managed in list(self.processes):
            self._terminate(managed)
        self._cleanup_dead()

    def run(self) -> None:
        logger.info(
            "Worker pool manager started (queue=%s, min=%s, max=%s, key=%s, name_prefix=%s)",
            ",".join(QUEUE_NAMES),
            MIN_WORKERS,
            MAX_WORKERS,
            DESIRED_KEY,
            NAME_PREFIX,
        )
        while self._running:
            try:
                desired = self._read_desired_count()
                self._reconcile(desired)
                self._publish_heartbeat(desired)
            except Exception as exc:
                logger.error("Worker pool loop failed: %s", exc)
            time.sleep(POLL_SECONDS)


manager = WorkerPoolManager()


def _handle_signal(signum, _frame):
    logger.info("Received signal %s, shutting down worker pool manager", signum)
    manager.stop()


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


if __name__ == "__main__":
    try:
        manager.run()
    finally:
        manager.stop()
