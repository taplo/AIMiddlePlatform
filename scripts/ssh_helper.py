#!/usr/bin/env python3
"""SSH helper — run commands and copy files to remote hosts via paramiko."""

import io
import os
import sys
import time

import paramiko

HOSTS = {
    "122": {"hostname": "192.168.3.122", "port": 22},
    "123": {"hostname": "192.168.3.123", "port": 22},
}
USERNAME = "taplo"
PASSWORD = "rake.t.wang"

PROXY_HTTP = "http://192.168.3.208:8787"
PROXY_SOCKS = "socks5://192.168.3.208:8888"

_SSH_CACHE: dict[str, paramiko.SSHClient] = {}


def get_ssh(host_key: str) -> paramiko.SSHClient:
    if host_key not in _SSH_CACHE:
        info = HOSTS[host_key]
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(info["hostname"], port=info["port"], username=USERNAME, password=PASSWORD, timeout=15)
        _SSH_CACHE[host_key] = client
        print(f"[{host_key}] Connected to {info['hostname']}", file=sys.stderr)
    return _SSH_CACHE[host_key]


def run(host_key: str, command: str, timeout: int = 30) -> tuple[int, str, str]:
    ssh = get_ssh(host_key)
    _, stdout, stderr = ssh.exec_command(command, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    return exit_code, out, err


def put(host_key: str, local_path: str, remote_path: str):
    ssh = get_ssh(host_key)
    sftp = ssh.open_sftp()
    sftp.put(local_path, remote_path)
    sftp.close()
    print(f"[{host_key}] Uploaded {local_path} → {remote_path}", file=sys.stderr)


def put_bytes(host_key: str, data: bytes, remote_path: str):
    ssh = get_ssh(host_key)
    sftp = ssh.open_sftp()
    with sftp.open(remote_path, "wb") as f:
        f.write(data)
    sftp.close()
    print(f"[{host_key}] Uploaded {len(data)} bytes → {remote_path}", file=sys.stderr)


def get(host_key: str, remote_path: str, local_path: str):
    ssh = get_ssh(host_key)
    sftp = ssh.open_sftp()
    sftp.get(remote_path, local_path)
    sftp.close()
    print(f"[{host_key}] Downloaded {remote_path} → {local_path}", file=sys.stderr)


def check(host_key: str) -> dict:
    result = {}
    tests = [
        ("os", "cat /etc/os-release 2>/dev/null | head -3"),
        ("docker", "docker --version 2>&1"),
        ("docker_compose", "docker compose version 2>&1"),
        ("python", "python3 --version 2>&1"),
        ("pip", "pip3 --version 2>&1"),
        ("git", "git --version 2>&1"),
        ("cpu_info", "lscpu 2>/dev/null | grep 'Model name' | head -1"),
        ("memory", "free -h 2>/dev/null | grep Mem"),
        ("disk", "df -h / 2>/dev/null | tail -1"),
        ("hostname", "hostname"),
    ]
    for key, cmd in tests:
        _, out, err = run(host_key, cmd, timeout=10)
        result[key] = out or err
    return result


def close_all():
    for key, client in _SSH_CACHE.items():
        client.close()
        print(f"[{key}] Disconnected", file=sys.stderr)
    _SSH_CACHE.clear()


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "check"
    host_key = sys.argv[2] if len(sys.argv) > 2 else "all"
    targets = list(HOSTS.keys()) if host_key == "all" else [host_key]

    for hk in targets:
        if action == "check":
            info = check(hk)
            print(f"\n{'='*50}")
            print(f"Host: {hk} ({HOSTS[hk]['hostname']})")
            print(f"{'='*50}")
            for k, v in info.items():
                print(f"  {k:20s} = {v}")
        elif action == "run":
            cmd = " ".join(sys.argv[3:]) if len(sys.argv) > 3 else ""
            code, out, err = run(hk, cmd)
            print(f"[{hk}] exit={code}")
            if out:
                print(out)
            if err:
                print("STDERR:", err[:500], file=sys.stderr)
        else:
            print(f"Unknown action: {action}")

    close_all()
