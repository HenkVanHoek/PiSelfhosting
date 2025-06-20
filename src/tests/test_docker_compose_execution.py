# tests/test_docker_compose_execution.py
import pytest
from unittest.mock import MagicMock, patch
import io

# Import the function that will be tested from src/setup.py
# We will create a stub for this function in src/setup.py first.
from src.setup import run_docker_compose_command, get_project_root  # The function we are testing


# --- Fixtures for Mocking SSH Client ---

@pytest.fixture
def mock_ssh_client():
    """
    Mocks a paramiko.SSHClient instance and its exec_command method.
    """
    mock_client = MagicMock()
    mock_channel = MagicMock()  # Represents stdout.channel in exec_command

    # Configure the return value for exec_command
    # exec_command returns (stdin, stdout, stderr) file-like objects
    # We need to simulate their behavior
    mock_stdin = MagicMock()
    mock_stdout = MagicMock(spec=io.StringIO)  # Mock stdout to behave like a StringIO
    mock_stderr = MagicMock(spec=io.StringIO)  # Mock stderr to behave like a StringIO

    # Configure stdout to return lines when read
    mock_stdout.readline.side_effect = ["Creating network \"piselfhosting_default\" with the default driver",
                                        "Creating homeassistant ... done",
                                        ""]  # Empty string to signal end of stream

    # Configure stderr if we want to test error scenarios
    mock_stderr.read.return_value = ""  # No errors for successful run

    # Configure the exit status of the command
    mock_channel.recv_exit_status.return_value = 0  # 0 for success

    # Tie stdout to channel for exit status
    mock_stdout.channel = mock_channel

    mock_client.exec_command.return_value = (mock_stdin, mock_stdout, mock_stderr)
    return mock_client


# --- Test for run_docker_compose_command ---

@patch('src.setup.get_project_root', return_value='/mock/pi/project')  # Patch project root
def test_run_docker_compose_up_success(
    mock_get_project_root,
    mock_ssh_client # <--- Pass the fixture directly as the instance
):
    """
    Tests that run_docker_compose_command correctly executes 'docker compose up -d'
    and returns success.
    """
    # The mock_ssh_client fixture itself is already the mock instance.
    # No need for: mock_ssh_client_class.return_value = mock_ssh_client()

    project_path = '/mock/pi/project'
    command_to_run = 'up -d' # The specific docker compose command

    # Call the function, passing the mock_ssh_client instance
    success, stdout_output, stderr_output = run_docker_compose_command(
        mock_ssh_client, # <--- Pass the mock_ssh_client instance directly
        command_to_run
    )

    # Assertions
    assert success is True, "Command should have succeeded"
    assert "Creating homeassistant ... done" in stdout_output, "Expected success message not found in stdout"
    assert "Creating network \"piselfhosting_default\" with the default driver" in stdout_output
    assert stderr_output == "", "Stderr should be empty for a successful command"

    # Verify that exec_command was called with the correct full command
    expected_full_command = f"cd {project_path} && docker compose {command_to_run}"
    # Assert on the mock_ssh_client instance directly
    mock_ssh_client.exec_command.assert_called_once_with(expected_full_command, get_pty=True)

@patch('src.setup.get_project_root', return_value='/mock/pi/project')
def test_run_docker_compose_failure(
        mock_get_project_root,
        mock_ssh_client
):
    """
    Tests that run_docker_compose_command handles a failed docker compose command.
    """
    mock_client = mock_ssh_client.return_value  # Get the mock client
    mock_client.exec_command.return_value = (
        MagicMock(),  # stdin
        MagicMock(readline=lambda: "", channel=MagicMock(recv_exit_status=lambda: 1)),
        # stdout (empty, but exit code 1)
        MagicMock(read=lambda: "Error: Something went wrong with Docker Compose")  # stderr
    )

    project_path = '/mock/pi/project'
    command_to_run = 'up -d'

    success, stdout_output, stderr_output = run_docker_compose_command(
        mock_client,
        command_to_run
    )

    assert success is False, "Command should have failed"
    assert stdout_output == "", "Stdout should be empty for this failure test"
    assert "Error: Something went wrong with Docker Compose" in stderr_output, "Expected error message not found in stderr"

    expected_full_command = f"cd {project_path} && docker compose {command_to_run}"
    mock_client.exec_command.assert_called_once_with(expected_full_command, get_pty=True)