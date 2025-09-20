# In src/managers/ssh_manager.py

import select
from typing import Callable, Optional, Tuple

import paramiko
from paramiko import SFTPClient, SSHClient


class SSHManager:
    """Manages SSH connections and command execution on a remote host."""

    def __init__(self, hostname: str, username: str, password: str, port: int = 22):
        self.hostname = hostname
        self.username = username
        self.password = password
        self.port = port
        self.client: Optional[SSHClient] = None
        # --- FIX: Added type hint for SFTP client to resolve mypy errors ---
        self.sftp: Optional[SFTPClient] = None

    def connect(self) -> Tuple[bool, str]:
        """Establishes the SSH connection."""
        try:
            self.client = SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # nosec
            self.client.connect(
                hostname=self.hostname,
                username=self.username,
                password=self.password,
                port=self.port,
                timeout=10,
            )
            return True, "Connection successful."
        except Exception as e:
            self.client = None
            return False, str(e)

    def execute_command(
        self,
        command: str,
        log_callback: Callable[..., None],
        *,
        check_exit_code: bool = True,
    ) -> Tuple[int, str]:
        """Executes a command on the remote host, streaming output."""
        if not self.client:
            log_callback("FATAL: SSH client not connected.\n")
            return -1, ""

        try:
            # --- FIX: Check that transport is active to fix mypy [union-attr] ---
            transport = self.client.get_transport()
            if not transport:
                log_callback("FATAL: SSH transport is not active.\n")
                return -1, ""

            channel = transport.open_session()
            channel.get_pty()  # Request a pseudo-terminal
            channel.exec_command(command)  # nosec B601

            stdout_parts = []
            # Loop and stream output...
            while not channel.exit_status_ready():
                readq, _, _ = select.select([channel], [], [], 0.2)
                if readq:
                    if channel.recv_ready():
                        chunk = channel.recv(4096).decode("utf-8", "ignore")
                        stdout_parts.append(chunk)
                        log_callback(chunk)
                    if channel.recv_stderr_ready():
                        chunk = channel.recv_stderr(4096).decode("utf-8", "ignore")
                        log_callback(chunk)

            exit_code = channel.recv_exit_status()

            if check_exit_code and exit_code != 0:
                short_cmd = f"{command[:40]}..." if len(command) > 40 else command
                log_callback(
                    f"ERROR: Command '{short_cmd}' failed with exit code {exit_code}\n"
                )

            full_stdout = "".join(stdout_parts).strip()
            return exit_code, full_stdout

        except Exception as e:
            log_callback(f"FATAL STREAMING ERROR: {e}\n")
            return -1, ""

    def upload_content(
        self, content_bytes: bytes, remote_path: str
    ) -> Tuple[bool, str]:
        """Uploads byte content to a file on the remote host."""
        if not self.client:
            return False, "Client not connected."
        try:
            self.sftp = self.client.open_sftp()
            with self.sftp.open(remote_path, "wb") as f:
                f.set_pipelined(True)
                f.write(content_bytes)
            return True, "File content uploaded successfully."
        except Exception as e:
            return False, str(e)
        finally:
            if self.sftp:
                self.sftp.close()

    def close(self) -> None:
        """Closes the SSH connection."""
        if self.client:
            self.client.close()
            self.client = None
