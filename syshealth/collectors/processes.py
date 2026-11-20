"""Running processes with CPU and memory usage."""

from __future__ import annotations

import os
import time

import psutil

from ..util import INFO, Finding

ATTRS = ["pid", "name", "username", "memory_info", "num_threads", "status",
         "create_time", "cmdline"]


def collect() -> dict:
    procs = []
    for p in psutil.process_iter():
        try:
            p.cpu_percent(None)
            procs.append(p)
        except psutil.Error:
            pass
    time.sleep(0.7)
    ncpu = psutil.cpu_count() or 1
    me = os.getuid()
    rows = []
    for p in procs:
        try:
            with p.oneshot():
                cpu = p.cpu_percent(None) / ncpu
                info = p.as_dict(ATTRS)
                uid = p.uids().real
        except psutil.Error:
            continue
        mem = info.get("memory_info")
        cmd = info.get("cmdline") or []
        if not cmd and (not mem or mem.rss == 0):
            continue  # kernel thread
        rows.append({
            "pid": info["pid"],
            "name": info.get("name") or "?",
            "user": info.get("username") or "?",
            "own": uid == me,
            "cpu": cpu,
            "rss": mem.rss if mem else 0,
            "threads": info.get("num_threads") or 0,
            "status": info.get("status") or "",
            "started": info.get("create_time"),
            "cmdline": " ".join(cmd),
        })
    rows.sort(key=lambda r: r["cpu"], reverse=True)

    findings = []
    zombies = [r for r in rows if r["status"] == psutil.STATUS_ZOMBIE]
    if len(zombies) >= 5:
        findings.append(Finding(INFO, f"{len(zombies)} zombie processes",
                                "Finished processes whose parent has not cleaned them up."))
    top = rows[0] if rows else None
    summary = f"{len(rows)} running"
    if top and top["cpu"] >= 1:
        summary += f" · top: {top['name']} {top['cpu']:.0f}%"
    return {
        "rows": rows,
        "total": len(rows),
        "threads": sum(r["threads"] for r in rows),
        "findings": findings,
        "summary": summary,
    }


def signal_process(pid: int, force: bool = False) -> str | None:
    """Ask a process to quit (SIGTERM) or kill it (SIGKILL). Returns an error or None."""
    try:
        p = psutil.Process(pid)
        if force:
            p.kill()
        else:
            p.terminate()
    except psutil.NoSuchProcess:
        return "The process has already exited."
    except psutil.AccessDenied:
        return "Permission denied: this process belongs to another user or to the system."
    return None
