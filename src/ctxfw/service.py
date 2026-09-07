"""
src/ctxfw/service.py — Background Service Manager for Windows & systemd (v3.5.0)
Provides native OS daemon lifecycle integration:
- Windows Service Manager (sc.exe)
- Linux / POSIX systemd unit file generator and systemctl controller
- Cross-platform detached background process daemon with PID tracking
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import time
from typing import Dict, Optional

import httpx

from ctxfw.storage.cache import get_canonical_cache_path


def get_pid_file_path() -> Path:
    """Returns the persistent PID file path for the detached background service."""
    return get_canonical_cache_path().parent / "ctxfw_service.pid"


def get_executable_command() -> str:
    """Returns the invocation path for ctxfw (binary or python entrypoint)."""
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).resolve())
    return f'"{sys.executable}" -m ctxfw.cli'


# =========================================================================
# Windows Service Manager (sc.exe)
# =========================================================================

class WindowsServiceManager:
    SERVICE_NAME = "ctxfw"
    DISPLAY_NAME = "Context Firewall Gateway"

    @classmethod
    def generate_install_command(cls, exe_path: Optional[str] = None) -> str:
        bin_path = exe_path or get_executable_command()
        return f'sc.exe create {cls.SERVICE_NAME} binPath= "{bin_path} proxy" start= auto DisplayName= "{cls.DISPLAY_NAME}"'

    @classmethod
    def install(cls, exe_path: Optional[str] = None) -> bool:
        cmd = cls.generate_install_command(exe_path)
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return p.returncode == 0

    @classmethod
    def start(cls) -> bool:
        p = subprocess.run(f"sc.exe start {cls.SERVICE_NAME}", shell=True, capture_output=True, text=True)
        return p.returncode == 0

    @classmethod
    def stop(cls) -> bool:
        p = subprocess.run(f"sc.exe stop {cls.SERVICE_NAME}", shell=True, capture_output=True, text=True)
        return p.returncode == 0

    @classmethod
    def query(cls) -> Dict[str, str]:
        p = subprocess.run(f"sc.exe query {cls.SERVICE_NAME}", shell=True, capture_output=True, text=True)
        output = p.stdout
        status = "STOPPED"
        if "RUNNING" in output:
            status = "RUNNING"
        elif "PAUSED" in output:
            status = "PAUSED"
        elif "PENDING" in output:
            status = "PENDING"
        elif "1060" in output:
            status = "NOT_INSTALLED"
        return {"service": cls.SERVICE_NAME, "status": status, "raw": output}

    @classmethod
    def uninstall(cls) -> bool:
        p = subprocess.run(f"sc.exe delete {cls.SERVICE_NAME}", shell=True, capture_output=True, text=True)
        return p.returncode == 0


# =========================================================================
# Linux / POSIX systemd Daemon
# =========================================================================

class SystemdServiceManager:
    SERVICE_NAME = "ctxfw.service"

    @classmethod
    def generate_unit_content(cls, exe_path: Optional[str] = None, user_mode: bool = False) -> str:
        bin_path = exe_path or get_executable_command()
        user_line = "" if user_mode else "User=ctxfw\nGroup=ctxfw\n"
        return f"""[Unit]
Description=Context Firewall Reverse Proxy Gateway (Zero-Python Sovereign Service)
After=network.target

[Service]
Type=simple
ExecStart={bin_path} proxy
Restart=always
RestartSec=3
MemoryMax=45M
{user_line}Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
"""

    @classmethod
    def get_unit_path(cls, user_mode: bool = False) -> Path:
        if user_mode:
            return Path.home() / ".config" / "systemd" / "user" / cls.SERVICE_NAME
        return Path("/etc/systemd/system") / cls.SERVICE_NAME

    @classmethod
    def install(cls, exe_path: Optional[str] = None, user_mode: bool = False) -> bool:
        unit_content = cls.generate_unit_content(exe_path, user_mode)
        unit_path = cls.get_unit_path(user_mode)
        try:
            unit_path.parent.mkdir(parents=True, exist_ok=True)
            unit_path.write_text(unit_content, encoding="utf-8")
            user_flag = "--user" if user_mode else ""
            subprocess.run(f"systemctl {user_flag} daemon-reload", shell=True, check=False)
            subprocess.run(f"systemctl {user_flag} enable {cls.SERVICE_NAME}", shell=True, check=False)
            return True
        except Exception:
            return False

    @classmethod
    def start(cls, user_mode: bool = False) -> bool:
        user_flag = "--user" if user_mode else ""
        p = subprocess.run(f"systemctl {user_flag} start {cls.SERVICE_NAME}", shell=True, check=False)
        return p.returncode == 0

    @classmethod
    def stop(cls, user_mode: bool = False) -> bool:
        user_flag = "--user" if user_mode else ""
        p = subprocess.run(f"systemctl {user_flag} stop {cls.SERVICE_NAME}", shell=True, check=False)
        return p.returncode == 0

    @classmethod
    def status(cls, user_mode: bool = False) -> Dict[str, str]:
        user_flag = "--user" if user_mode else ""
        p = subprocess.run(f"systemctl {user_flag} status {cls.SERVICE_NAME}", shell=True, capture_output=True, text=True)
        return {
            "service": cls.SERVICE_NAME,
            "status": "RUNNING" if p.returncode == 0 else "INACTIVE",
            "raw": p.stdout or p.stderr,
        }


# =========================================================================
# Cross-Platform Detached Background Daemon
# =========================================================================

class DetachedDaemonManager:

    @classmethod
    def start_detached(cls, port: int = 8080, host: str = "127.0.0.1") -> int:
        """Starts ctxfw proxy in a detached background process and saves PID."""
        pid_file = get_pid_file_path()
        if pid_file.is_file():
            try:
                old_pid = int(pid_file.read_text().strip())
                # Check if still running
                if platform.system() == "Windows":
                    p = subprocess.run(f"tasklist /FI \"PID eq {old_pid}\"", shell=True, capture_output=True, text=True)
                    if str(old_pid) in p.stdout:
                        return old_pid
                else:
                    os.kill(old_pid, 0)
                    return old_pid
            except Exception:
                pass

        cmd = [sys.executable, "-m", "ctxfw.proxy", "--port", str(port), "--host", host]
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "proxy", "--port", str(port), "--host", host]

        flags = 0
        if platform.system() == "Windows":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags if platform.system() == "Windows" else 0,
            start_new_session=True if platform.system() != "Windows" else False,
        )

        pid_file.write_text(str(proc.pid), encoding="utf-8")
        return proc.pid

    @classmethod
    def stop_detached(cls) -> bool:
        """Stops the detached background process."""
        pid_file = get_pid_file_path()
        if not pid_file.is_file():
            return False

        try:
            pid = int(pid_file.read_text().strip())
            if platform.system() == "Windows":
                subprocess.run(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                os.kill(pid, signal.SIGTERM)
            pid_file.unlink(missing_ok=True)
            return True
        except Exception:
            pid_file.unlink(missing_ok=True)
            return False

    @classmethod
    def check_health(cls, port: int = 8080) -> bool:
        """Checks if the proxy service is actively listening on health endpoint."""
        try:
            with httpx.Client(timeout=1.0) as client:
                r = client.get(f"http://127.0.0.1:{port}/health")
                return r.status_code == 200
        except Exception:
            return False


def handle_service_command(args: list[str]) -> int:
    """Dispatches `ctxfw service` subcommands."""
    parser = argparse.ArgumentParser(
        prog="ctxfw service",
        description="ctxfw service — Background Service Lifecycle Manager (Windows & systemd)",
    )
    parser.add_argument(
        "action",
        choices=["install", "uninstall", "start", "stop", "status", "generate"],
        help="Service lifecycle action",
    )
    parser.add_argument("--user", action="store_true", help="Use systemd user service on Linux")
    parser.add_argument("--port", type=int, default=8080, help="Proxy port")
    opts = parser.parse_args(args)

    system = platform.system()

    if opts.action == "generate":
        if system == "Windows":
            print("[*] Windows Service Command (Ejecutar como Administrador):")
            print(f"    {WindowsServiceManager.generate_install_command()}")
        else:
            print("[*] systemd Unit File Content:")
            print(SystemdServiceManager.generate_unit_content(user_mode=opts.user))
        return 0

    if system == "Windows":
        if opts.action == "install":
            ok = WindowsServiceManager.install()
            print(f"[*] Windows Service install: {'OK' if ok else 'FAILED (se requieren permisos de Administrador)'}")
            return 0 if ok else 1
        elif opts.action == "start":
            ok = WindowsServiceManager.start()
            print(f"[*] Windows Service start: {'OK' if ok else 'FAILED'}")
            return 0 if ok else 1
        elif opts.action == "stop":
            ok = WindowsServiceManager.stop()
            print(f"[*] Windows Service stop: {'OK' if ok else 'FAILED'}")
            return 0 if ok else 1
        elif opts.action == "status":
            info = WindowsServiceManager.query()
            print(f"[*] Service: {info['service']} | Status: {info['status']}")
            return 0
        elif opts.action == "uninstall":
            ok = WindowsServiceManager.uninstall()
            print(f"[*] Windows Service uninstall: {'OK' if ok else 'FAILED'}")
            return 0 if ok else 1
    else:
        # Linux / POSIX systemd
        if opts.action == "install":
            ok = SystemdServiceManager.install(user_mode=opts.user)
            print(f"[*] systemd install: {'OK' if ok else 'FAILED'}")
            return 0 if ok else 1
        elif opts.action == "start":
            ok = SystemdServiceManager.start(user_mode=opts.user)
            print(f"[*] systemd start: {'OK' if ok else 'FAILED'}")
            return 0 if ok else 1
        elif opts.action == "stop":
            ok = SystemdServiceManager.stop(user_mode=opts.user)
            print(f"[*] systemd stop: {'OK' if ok else 'FAILED'}")
            return 0 if ok else 1
        elif opts.action == "status":
            info = SystemdServiceManager.status(user_mode=opts.user)
            print(f"[*] Service: {info['service']} | Status: {info['status']}")
            return 0

    return 0
