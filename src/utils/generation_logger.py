import datetime
import json
from pathlib import Path
from typing import Any, Dict, List


class GenerationLogger:
    """
    Creates a detailed, human-readable log of a single file generation run.
    The log is a timestamped Markdown file for easy reading and comparison.
    """

    def __init__(self, output_dir: Path):
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        self.log_path = output_dir / f"generation-log-{timestamp}.md"
        self._log_content = []
        self.log_step("PiSelfhosting Configuration Generation Log")
        self._log_content.append(f"**Timestamp:** `{timestamp}`\n")

    def log_step(self, title: str):
        """Logs a major step in the process."""
        self._log_content.append(f"\n## {title}\n")

    def log_dict(self, name: str, data: Dict[str, Any]):
        """Logs a dictionary as a formatted JSON block."""
        self._log_content.append(f"### {name}\n")
        # Use json.dumps for pretty-printing the dictionary
        pretty_json = json.dumps(data, indent=2)
        self._log_content.append(f"```json\n{pretty_json}\n```\n")

    def log_list(self, name: str, data: List[str]):
        """Logs a list of strings."""
        self._log_content.append(f"### {name}\n")
        for item in data:
            self._log_content.append(f"- `{item}`\n")
        self._log_content.append("\n")

    def log_variable_resolution(self, defaults: Dict, overrides: Dict, final: Dict):
        """Logs the variable layering process for clarity."""
        self.log_step("Variable Resolution and Context Building")
        self.log_dict("1. Default Variables Loaded", defaults)
        self.log_dict("2. User Overrides Applied", overrides)
        self.log_dict("3. Final Render Context (Before Nested Resolution)", final)

    def write_log(self):
        """Writes the collected log content to the final Markdown file."""
        try:
            with open(self.log_path, "w") as f:
                f.write("\n".join(self._log_content))
        except IOError as e:
            # Log an error to the main application log if this fails
            print(
                f"CRITICAL: Failed to write generation log file at {self.log_path}: {e}"
            )
