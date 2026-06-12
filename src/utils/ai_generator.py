# src/utils/ai_generator.py

import json
import logging
import urllib.parse
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class AIGenerator:
    """Handles interaction with the Gemini REST API to generate components."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    def generate_component_data(
        self, repo_url: str, custom_instructions: Optional[str] = None
    ) -> dict:
        """Analyzes a GitHub repository and returns structured component configuration.

        Uses the Gemini REST API with structured JSON output configuration.
        """
        api_key = self.api_key or requests.utils.default_headers().get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("Gemini API key is not configured.")

        # Clean and validate the repository URL
        parsed_url = urllib.parse.urlparse(repo_url)
        if not parsed_url.netloc or "github.com" not in parsed_url.netloc:
            raise ValueError("A valid GitHub repository URL is required.")

        path_parts = [p for p in parsed_url.path.split("/") if p]
        if len(path_parts) < 2:
            raise ValueError(
                "Invalid repository URL format. Must contain owner and repository name."
            )

        owner = path_parts[0]
        repo_name = path_parts[1].replace(".git", "")
        component_id = repo_name.lower()

        # Compile System Prompt and instructions
        system_prompt = (
            "You are an expert Docker and PiSelfhosting configuration engineer.\n"
            "Your task is to analyze the target GitHub repository and generate the "
            "PiSelfhosting component files.\n\n"
            "Constraints:\n"
            "1. The component must run in Docker and join the external network "
            'named "piselfhosting_net".\n'
            "2. Expose external ports using configuration variables. "
            'For example, use "{{ CADDY_HTTP_PORT }}" for the host port mapping.\n'
            '3. Use "{{ DATA_ROOT }}" for host-side persistent data paths. '
            'For example: "{{ DATA_ROOT }}/caddy/data:/data".\n'
            "4. Do not include a version key in the "
            "generated Docker Compose template.\n"
            "5. If the service requires a default configuration file "
            "(such as a Caddyfile), define it in the config_templates "
            "property with its relative mount target.\n"
        )

        user_prompt = (
            f"Analyze the repository: {owner}/{repo_name} (URL: {repo_url}).\n"
        )
        if custom_instructions:
            user_prompt += f"Custom User Instructions: {custom_instructions}\n"

        prompt = f"{system_prompt}\n{user_prompt}"

        # Define the expected JSON response schema
        response_schema = {
            "type": "OBJECT",
            "properties": {
                "metadata": {
                    "type": "OBJECT",
                    "properties": {
                        "name": {"type": "STRING"},
                        "image_name": {"type": "STRING"},
                        "description": {"type": "STRING"},
                        "group": {"type": "STRING"},
                        "has_ui": {"type": "BOOLEAN"},
                        "has_configuration": {"type": "BOOLEAN"},
                        "conflicts_with": {
                            "type": "ARRAY",
                            "items": {"type": "STRING"},
                        },
                        "depends_on": {
                            "type": "ARRAY",
                            "items": {"type": "STRING"},
                        },
                        "tags": {
                            "type": "ARRAY",
                            "items": {"type": "STRING"},
                        },
                    },
                    "required": [
                        "name",
                        "image_name",
                        "description",
                        "group",
                        "has_ui",
                        "has_configuration",
                    ],
                },
                "docker_compose": {"type": "STRING"},
                "variables": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "id": {"type": "STRING"},
                            "label": {"type": "STRING"},
                            "type": {"type": "STRING"},
                            "default": {"type": "STRING"},
                            "description": {"type": "STRING"},
                        },
                        "required": ["id", "label", "type", "default", "description"],
                    },
                },
                "config_templates": {
                    "type": "OBJECT",
                    "additionalProperties": {"type": "STRING"},
                },
            },
            "required": ["metadata", "docker_compose", "variables"],
        }

        # Build payload for the API
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": response_schema,
            },
        }

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.5-flash:generateContent?key={api_key}"
        )

        try:
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
            result_json = response.json()

            # Retrieve generated content from the response structure
            candidates = result_json.get("candidates", [])
            if not candidates:
                raise ValueError("No candidates returned from Gemini API.")

            # Apply Unpacking-First Mandate from rules
            candidate, *_ = candidates
            content = candidate.get("content", {})
            parts = content.get("parts", [])
            if not parts:
                raise ValueError("No parts found in the response content.")

            part, *_ = parts
            text = part.get("text", "")

            # Parse and validate the returned JSON
            data = json.loads(text)
            data["id"] = component_id
            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"Gemini API request failed: {e}")
            raise RuntimeError(f"Failed to communicate with Gemini API: {e}")
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to parse Gemini API response: {e}")
            raise RuntimeError(f"Received malformed response from Gemini API: {e}")
