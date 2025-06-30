# run_pytest_wrapper.py
import os
import sys
import pytest

project_root = os.path.abspath(os.path.dirname(__file__))
src_path = os.path.join(project_root, 'src')

if src_path not in sys.path:
    sys.path.insert(0, src_path)

# Arguments to pass to pytest.
# Keep it simple here to ensure default pytest behavior.
# We explicitly list the test path, and no output-suppressing flags.
pytest_args = [
    str(os.path.join(project_root, 'tests')) # Pass the test directory as a string
]

# Als je de --no-header en --no-summary wilt behouden, kun je ze HIER toevoegen:
# pytest_args.append('--no-header')
# pytest_args.append('--no-summary')


print(f"Running pytest with arguments: {pytest_args} from working directory: {os.getcwd()}")

# Call pytest.main(). This should trigger full output for failures.
# By default, pytest.main() uses sys.argv if no arguments are given.
# We pass our constructed list.
exit_code = pytest.main(pytest_args)

sys.exit(exit_code)