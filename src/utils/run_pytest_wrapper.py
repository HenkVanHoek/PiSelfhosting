# src/utils/run_pytest_wrapper.py
import os
import sys

import pytest

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

src_path = os.path.join(project_root, "src")

if src_path not in sys.path:
    sys.path.insert(0, src_path)

# Arguments to pass to pytest.
# Keep it simple here to ensure default pytest behavior.
# We explicitly list the test path, and no output-suppressing flags.
tests_path = os.path.join(project_root, "tests")
pytest_args = [str(tests_path)]
# If you want to keep --no-header and --no-summary, you can add them HERE:
# pytest_args.append('--no-header')
# pytest_args.append('--no-summary')


print(f"Running pytest with arguments: {pytest_args}")
print(f"from working directory: {os.getcwd()}")

# Call pytest.main(). This should trigger full output for failures.
# By default, pytest.main() uses sys.argv if no arguments are given.
# We pass our constructed list.
exit_code = pytest.main(pytest_args)

sys.exit(exit_code)
