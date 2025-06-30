# tests/test_piselfhosting_installer.py (FINALE VERSIE 5.0 - ALL-IN)
import pytest
import os
import sys
from unittest.mock import patch, MagicMock
import json
import time

# Voeg de project-root toe aan het pad zodat de installer gevonden kan worden
current_test_file_dir = os.path.dirname(os.path.abspath(__file__))
project_root_from_test_dir = os.path.dirname(current_test_file_dir)
if project_root_from_test_dir not in sys.path:
    sys.path.insert(0, project_root_from_test_dir)

import piselfhosting_installer as installer


# --- Fixtures ---

@pytest.fixture
def mock_ssh_client():
    with patch('paramiko.SSHClient') as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.set_missing_host_key_policy = MagicMock()
        mock_client.connect = MagicMock()

        # Realistische mock voor exec_command die een werkend channel object teruggeeft
        mock_stdout = MagicMock()
        mock_stdout.read.return_value = b'stdout_output'
        mock_stdout.channel.recv_exit_status.return_value = 0  # Succes status

        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b''

        mock_client.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)
        mock_client.open_sftp.return_value = MagicMock()
        yield mock_client


@pytest.fixture
def mock_getenv():
    with patch('os.getenv') as mock_get:
        mock_get.side_effect = lambda key, default=None: {
            'PI_IP': '192.168.1.10', 'SSH_USERNAME': 'pi', 'SSH_PASSWORD': 'testpassword',
            'DOMAIN': 'yourdomain.com', 'PUID': '1000', 'PGID': '1000',
            'HOST_IP': '192.168.1.100', 'DB_USER': 'testdbuser', 'DB_PASS': 'testpassword',
            'TZ': 'Europe/London', 'ADMIN_EMAIL': 'admin@yourdomain.com',
            'FRIGATE_RTSP_PASSWORD': 'testpassword', 'PHPMYADMIN_BLOWFISH_SECRET': 'testsecret',
            'PMA_HOST': 'testmariadb', 'PISELFHOSTING_REUSE_VARIABLES': 'false',
        }.get(key, default)
        yield mock_get


@pytest.fixture
def mock_input(monkeypatch):
    inputs = []

    def fake_input(prompt):
        if not inputs: return '3'
        return inputs.pop(0)

    monkeypatch.setattr('builtins.input', fake_input)
    return inputs


@pytest.fixture
def mock_getpass(monkeypatch):
    passwords = []

    def fake_getpass(prompt):
        if passwords: return passwords.pop(0)
        return "default_password"

    monkeypatch.setattr('getpass.getpass', fake_getpass)
    return passwords


@pytest.fixture
def mock_set_key():
    with patch('dotenv.set_key') as mock_sk: yield mock_sk


@pytest.fixture
def mock_urandom():
    with patch('os.urandom') as mock_u: mock_u.return_value = b'\x01' * 32; yield mock_u


@pytest.fixture
def mock_run_remote_command_global():
    with patch('piselfhosting_installer.run_remote_command') as mock_rc:
        mock_rc.return_value = (True, '', '')
        yield mock_rc


# --- Tests ---

def test_get_user_input(mock_input):
    mock_input.append('user_val')
    assert installer.get_user_input("Prompt", "default") == "user_val"


def test_get_user_input_default(mock_input):
    mock_input.append('')
    assert installer.get_user_input("Prompt", "default") == "default"


@patch('socket.socket')
def test_get_local_ip_address_success(mock_socket_class):
    mock_socket_instance = mock_socket_class.return_value.__enter__.return_value
    mock_socket_instance.getsockname.return_value = ('192.168.1.50', 12345)
    assert installer.get_local_ip_address() == '192.168.1.50'


@patch('socket.socket', side_effect=Exception("Network error"))
def test_get_local_ip_address_failure(mock_socket_class):
    assert installer.get_local_ip_address() is None


# OPLOSSING: De @patch decorators voor Thread en Event zijn verwijderd.
@patch('time.sleep')
def test_run_remote_command_success(mock_sleep, mock_ssh_client):
    success, stdout, _ = installer.run_remote_command(mock_ssh_client, "echo hello")
    assert success is True
    assert stdout == "stdout_output"
    mock_ssh_client.exec_command.assert_called_with("echo hello")


def test_is_excluded_directory():
    installer.EXCLUDED_ITEMS = ['dir_to_exclude/']
    assert installer._is_excluded('/project_root/dir_to_exclude/sub_file.txt', '/project_root',
                                  installer.EXCLUDED_ITEMS) is True


@patch('os.walk')
def test_sync_files_to_pi_respects_exclusions(mock_walk, mock_ssh_client, mock_run_remote_command_global):
    mock_sftp = mock_ssh_client.open_sftp.return_value
    mock_walk.return_value = [
        ('/local/path', ['subdir1'], ['file1.txt', 'excluded_file.txt']),
        ('/local/path/subdir1', [], ['subfile1.txt']),
    ]
    installer.EXCLUDED_ITEMS = ['subdir1/', 'excluded_file.txt']
    installer.sync_files_to_pi(mock_ssh_client, '/local/path', '/remote/path')

    expected_local = '/local/path/file1.txt'
    expected_remote_normalized = os.path.normpath('/remote/path/file1.txt')

    mock_sftp.put.assert_called_once()
    actual_call = mock_sftp.put.call_args
    assert actual_call.args[0] == expected_local
    assert os.path.normpath(actual_call.args[1]) == expected_remote_normalized


@patch('piselfhosting_installer.sync_files_to_pi')
def test_main_function_flow(mock_sync, mock_run_remote_command_global, mock_ssh_client, mock_input, mock_getpass,
                            mock_getenv, mock_set_key, mock_urandom):
    # Deze test vangt de SystemExit af die aan het einde van main() wordt verwacht.
    with pytest.raises(SystemExit):
        mock_input.extend([
            'pi.local', 'pi', 'password', 'mydomain.com', '1000', '1000',
            'Europe/Amsterdam', 'admin@email.com', '192.168.1.10',
            'dbuser', 'dbpass', 'frigatepass', '3'  # Exit
        ])
        mock_getpass.extend(['password', 'dbpass', 'frigatepass'])

        mock_run_remote_command_global.side_effect = [
            (True, '/home/pi', ''),
            (True, 'Linux...', ''),
            (True, '/usr/bin/docker', ''),
            (True, 'active', ''),
            (True, 'pi docker', ''),
            (True, '', ''),
            (True, '', ''),
            (True, 'Build success', ''),
            (True, json.dumps({}), ''),
        ]

        installer.main()