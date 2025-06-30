# run_pytest_wrapper.py
import os
import sys
import pytest

# Ensure the project root and src/ directory are on the Python path
# This script is in the project root, so os.path.dirname(__file__) is the project root.
project_root = os.path.abspath(os.path.dirname(__file__))
src_path = os.path.join(project_root, 'src')

if src_path not in sys.path:
    sys.path.insert(0, src_path)

# Define the arguments to pass to pytest
# This is the path to your tests/ directory, relative to project_root
pytest_args = [
    os.path.join(project_root, 'tests'),
    '--no-header',
    '--no-summary',
    '-q'
]

# Run pytest
# pytest.main() returns an exit code. sys.exit() uses this code.
print(f"Running pytest with arguments: {pytest_args} from working directory: {os.getcwd()}")
sys.exit(pytest.main(pytest_args))