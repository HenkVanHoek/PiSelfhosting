import paramiko
import select


class SSHManager:
    def __init__(self, hostname, username, password, port=22):
        self.hostname = hostname
        self.username = username
        self.password = password
        self.port = port
        self.client = None

    def connect(self):
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(hostname=self.hostname, username=self.username,
                                password=self.password, port=self.port,
                                timeout=10)
            return True, "Connection successful."
        except Exception as e:
            self.client = None
            return False, str(e)

    def execute_command(self, command, callback):
        if not self.client:
            callback("FATAL: SSH client not connected.\n")
            return -1, ""

        try:
            channel = self.client.get_transport().open_session()
            channel.get_pty()
            channel.exec_command(command)

            stdout_parts = []
            stderr_parts = []

            # Read until the channel is closed
            while not channel.exit_status_ready():
                # Use select for non-blocking I/O
                readq, _, _ = select.select([channel], [], [], 0.2)
                if readq:
                    if channel.recv_ready():
                        chunk = channel.recv(4096).decode('utf-8', 'ignore')
                        stdout_parts.append(chunk)
                        callback(chunk)
                    if channel.recv_stderr_ready():
                        chunk = channel.recv_stderr(4096).decode('utf-8',
                                                                 'ignore')
                        stderr_parts.append(chunk)
                        callback(chunk)

            exit_code = channel.recv_exit_status()
            # Concatenate all captured parts for the final return value
            full_stdout = "".join(stdout_parts).strip()
            return exit_code, full_stdout

        except Exception as e:
            callback(f"FATAL STREAMING ERROR: {e}\n")
            return -1, ""

    def upload_content(self, content_bytes, remote_path):
        if not self.client: return False, "Client not connected."
        sftp = None
        try:
            sftp = self.client.open_sftp()
            with sftp.open(remote_path, 'wb') as f:
                f.write(content_bytes)
            return True, "File content uploaded successfully."
        except Exception as e:
            return False, str(e)
        finally:
            if sftp: sftp.close()

    def close(self):
        if self.client:
            self.client.close()
            self.client = None