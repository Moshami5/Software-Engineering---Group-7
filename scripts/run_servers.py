"""Start the three Task 6 servers with one command, and optionally check them end to end.

    interface :8000  -> orchestrator :8001  <- AI server :8002     (tasks/task6/README.md)

Each server is its own process (python -m uvicorn ...), so they stay separate servers
that only talk over HTTP; this script only starts them, waits until they answer and
stops them again. It never imports the servers itself.

Usage (from the repo root):
    python scripts/run_servers.py                     # start all three; Ctrl+C stops them
    python scripts/run_servers.py --check             # start, run the end-to-end check, stop
    python scripts/run_servers.py --check --no-interface
        # only orchestrator + AI server; the check sends the job to the orchestrator itself.
        # For use until the interface server is merged.

The end-to-end check (--check) sends requests the way a student would:
  1. invalid input (empty interest) to POST /advice -> 422, and no job reaches the queue;
  2. a real request ("software developer", 20 weeks) to POST /advice -> 202 + job id;
  3. polls GET /advice/{id} until the job is done -> result "ok" with 1-5 study paths,
     and the AI server's /health shows it handled one more job.
It exits with 0 when every step passes and 1 otherwise, so it can run in CI.

Server output goes to runtime/logs/<server>.log (runtime/ is not committed).
--check uses a fresh SQLite queue in runtime/, so old jobs from earlier runs cannot get
in the way; a normal start uses the orchestrator's default queue file.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
LOGS = RUNTIME / "logs"
HOST = "127.0.0.1"


@dataclass(frozen=True)
class Server:
    name: str
    app: str        # uvicorn "module:attribute"
    port: int
    health: str     # path that answers once the server is ready

    @property
    def url(self) -> str:
        return f"http://{HOST}:{self.port}"


# Ports and module names as agreed in tasks/task6/README.md.
ORCHESTRATOR = Server("orchestrator", "src.servers.orchestrator:app", 8001, "/health")
AI_SERVER = Server("ai_server", "src.servers.ai_server:app", 8002, "/health")
INTERFACE = Server("interface", "src.servers.interface_server:app", 8000, "/docs")

# Started in this order: the queue first, so the AI server and the interface find it.
ALL_SERVERS = (ORCHESTRATOR, AI_SERVER, INTERFACE)

GOOD_REQUEST = {"interest": "software developer", "weeks_available": 20}
BAD_REQUEST = {"interest": ""}
MAX_PATHS = 5  # src/paths.py: MIN_PATHS, MAX_PATHS = 3, 5


class CheckFailed(Exception):
    """One step of the end-to-end check did not give the agreed answer."""


# --------------------------------------------------------------------------- starting


def start(server: Server, env: dict[str, str]) -> subprocess.Popen:
    LOGS.mkdir(parents=True, exist_ok=True)
    log = open(LOGS / f"{server.name}.log", "w", encoding="utf-8")  # noqa: SIM115 - closed with the process
    cmd = [sys.executable, "-m", "uvicorn", server.app, "--host", HOST, "--port", str(server.port)]
    return subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)


def wait_until_up(server: Server, process: subprocess.Popen, timeout: float,
                  client: httpx.Client | None = None) -> None:
    """Wait until ``server`` answers its health path; fail early if its process exits.

    The AI server only starts answering after it has loaded the models (~30 s).
    """
    client = client or httpx.Client(timeout=2)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise CheckFailed(f"{server.name} stopped with exit code {process.returncode}; "
                              f"see {LOGS / (server.name + '.log')}")
        try:
            if client.get(server.url + server.health).status_code < 500:
                return
        except httpx.HTTPError:
            pass  # not listening yet
        time.sleep(0.5)
    raise CheckFailed(f"{server.name} did not answer on {server.url} within {timeout:.0f} s")


def stop_all(processes: list[subprocess.Popen]) -> None:
    for process in reversed(processes):
        if process.poll() is None:
            process.terminate()
    for process in processes:
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def port_in_use(port: int) -> bool:
    try:
        httpx.get(f"http://{HOST}:{port}/", timeout=1)
        return True
    except httpx.HTTPError:
        return False


# ----------------------------------------------------------------------- the check


def poll_until_finished(client: httpx.Client, url: str, timeout: float) -> dict:
    """GET ``url`` until the job status is done or failed."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(url)
        if response.status_code != 200:
            raise CheckFailed(f"GET {url} -> {response.status_code}: {response.text}")
        job = response.json()
        if job.get("status") in ("done", "failed"):
            return job
        time.sleep(0.5)
    raise CheckFailed(f"job at {url} not finished within {timeout:.0f} s")


def check_result(job: dict) -> dict:
    """The finished job must hold an advisor result with 1-5 study paths."""
    if job.get("status") != "done":
        raise CheckFailed(f"job {job.get('id')} {job.get('status')}: {job.get('error')}")
    result = job.get("result") or {}
    if result.get("ok") is not True:
        raise CheckFailed(f"advisor refused the request: {result.get('error')}")
    paths = result.get("paths") or []
    if not 1 <= len(paths) <= MAX_PATHS:
        raise CheckFailed(f"expected 1-{MAX_PATHS} study paths, got {len(paths)}")
    if not all(path.get("courses") for path in paths):
        raise CheckFailed("a study path has no courses")
    return result


def jobs_handled(client: httpx.Client) -> int:
    stats = client.get(AI_SERVER.url + "/health").json()
    return stats["jobs_done"] + stats["jobs_failed"]


def queued_jobs(client: httpx.Client) -> int:
    return sum(client.get(ORCHESTRATOR.url + "/health").json()["jobs"].values())


def run_check(client: httpx.Client, via_interface: bool = True, timeout: float = 120) -> dict:
    """The end-to-end check. Returns the advisor result; raises CheckFailed on any problem."""
    handled_before = jobs_handled(client)

    if via_interface:
        # 1. The interface must reject bad input itself: 422 and no job in the queue.
        queued_before = queued_jobs(client)
        response = client.post(INTERFACE.url + "/advice", json=BAD_REQUEST)
        if response.status_code != 422:
            raise CheckFailed(f"empty interest: expected 422, got {response.status_code}")
        if queued_jobs(client) != queued_before:
            raise CheckFailed("empty interest was rejected but still reached the queue")
        print("  ok  invalid input rejected by the interface (422), no job created")

        # 2. A real request goes in through the interface ...
        response = client.post(INTERFACE.url + "/advice", json=GOOD_REQUEST)
        if response.status_code != 202:
            raise CheckFailed(f"POST /advice: expected 202, got {response.status_code}: {response.text}")
        status_url = f"{INTERFACE.url}/advice/{response.json()['id']}"
    else:
        response = client.post(ORCHESTRATOR.url + "/jobs", json={"request": GOOD_REQUEST})
        if response.status_code != 201:
            raise CheckFailed(f"POST /jobs: expected 201, got {response.status_code}: {response.text}")
        status_url = f"{ORCHESTRATOR.url}/jobs/{response.json()['id']}"
    print(f"  ok  request accepted: {status_url}")

    # 3. ... and comes back with study paths, computed by the AI server.
    result = check_result(poll_until_finished(client, status_url, timeout))
    if jobs_handled(client) != handled_before + 1:
        raise CheckFailed("the job finished but the AI server did not report handling it")
    print(f"  ok  {len(result['paths'])} study paths returned, computed by the AI server")
    return result


# ------------------------------------------------------------------------------ main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true",
                        help="run the end-to-end check, then stop the servers")
    parser.add_argument("--no-interface", action="store_true",
                        help="start only the orchestrator and AI server")
    parser.add_argument("--timeout", type=float, default=180,
                        help="seconds to wait for each server to start (default 180)")
    args = parser.parse_args(argv)

    servers = [s for s in ALL_SERVERS if not (args.no_interface and s is INTERFACE)]
    busy = [s for s in servers if port_in_use(s.port)]
    if busy:
        print("Port already in use: " + ", ".join(f"{s.name} :{s.port}" for s in busy)
              + ". Stop the old servers first.", file=sys.stderr)
        return 1

    env = dict(os.environ, ORCHESTRATOR_URL=ORCHESTRATOR.url)
    if args.check:
        RUNTIME.mkdir(exist_ok=True)
        db = RUNTIME / "e2e_check.sqlite3"
        db.unlink(missing_ok=True)
        env["ORCHESTRATOR_DB"] = str(db)

    processes: list[subprocess.Popen] = []
    try:
        for server in servers:
            print(f"starting {server.name} on {server.url} ...", flush=True)
            processes.append(start(server, env))
            wait_until_up(server, processes[-1], args.timeout)
        print(f"all {len(servers)} servers up; logs in {LOGS}")

        if args.check:
            print("end-to-end check:")
            with httpx.Client(timeout=10) as client:
                run_check(client, via_interface=not args.no_interface)
            print("PASSED")
            return 0

        print("Ctrl+C stops all servers.")
        while all(p.poll() is None for p in processes):
            time.sleep(1)
        print("a server stopped; see the logs", file=sys.stderr)
        return 1
    except CheckFailed as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        stop_all(processes)
        print("servers stopped")


if __name__ == "__main__":
    sys.exit(main())
