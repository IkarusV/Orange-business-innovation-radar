from __future__ import annotations

import json
import re
import time
from collections.abc import Callable

import requests


class AIError(RuntimeError):
    pass


class APIBudgetError(AIError):
    pass


def _json_object(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError as error:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise AIError("The model did not return a JSON object.") from error
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise AIError("The model response must be a JSON object.")
    return value


def _responses_text(payload: dict) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    parts = []
    for output in payload.get("output", []):
        for content in output.get("content", []):
            text = content.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts)


class AIClient:
    def __init__(self, settings: dict):
        self.base_url = settings["base_url"].rstrip("/")
        self.api_key = settings["api_key"]
        self.model = settings["model"]
        self.mode = settings.get("mode", "auto")
        self.timeout = settings.get("timeout", 90)
        self.max_requests = int(settings.get("max_requests", 5))
        self.requests_per_minute = max(1, min(10, int(settings.get("requests_per_minute", 10))))
        self.request_count = 0
        self.last_request_at: float | None = None
        self.on_rate_limit_wait: Callable[[float], None] | None = None

    def _post(self, endpoint: str, payload: dict) -> dict:
        if not self.api_key:
            raise AIError("No API key configured. Add RADAR_AI_API_KEY or use the UI session setting.")
        if self.request_count >= self.max_requests:
            raise APIBudgetError(f"Hard API request budget reached ({self.max_requests}).")
        minimum_interval = 60 / self.requests_per_minute
        if self.last_request_at is not None:
            wait_seconds = max(0.0, minimum_interval - (time.monotonic() - self.last_request_at))
            if wait_seconds:
                if self.on_rate_limit_wait:
                    self.on_rate_limit_wait(wait_seconds)
                time.sleep(wait_seconds)
        self.request_count += 1
        self.last_request_at = time.monotonic()
        response = requests.post(
            f"{self.base_url}/{endpoint}",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=self.timeout,
        )
        if not response.ok:
            # Do not include headers or request data because they contain credentials.
            raise AIError(f"Provider returned HTTP {response.status_code}: {response.text[:400]}")
        return response.json()

    def generate_json(self, system_prompt: str, user_prompt: str) -> dict:
        errors = []
        modes = [self.mode] if self.mode != "auto" else ["responses", "chat"]
        for mode in modes:
            try:
                if mode == "responses":
                    payload = self._post("responses", {"model": self.model, "instructions": system_prompt, "input": user_prompt})
                    return _json_object(_responses_text(payload))
                payload = self._post("chat/completions", {
                    "model": self.model,
                    "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                    "response_format": {"type": "json_object"},
                })
                return _json_object(payload["choices"][0]["message"]["content"])
            except (AIError, KeyError, TypeError, requests.RequestException) as error:
                errors.append(f"{mode}: {error}")
                if self.mode != "auto" or "HTTP 404" not in str(error):
                    break
        raise AIError("; ".join(errors))
