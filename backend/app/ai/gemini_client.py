"""Google AI Studio (Gemini) client using the REST API via httpx."""

import json
import logging
import re
import time
from datetime import date

import httpx
from pydantic import ValidationError

from app.ai import prompts
from app.ai.llm_base import LLMClient, LLMError, LLMOutputError
from app.ai.schemas import EmailAnalysisResult


logger = logging.getLogger(__name__)

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# Temporary server errors that are safe to retry.
# 429 is NOT retried automatically because it can indicate
# quota/rate-limit exhaustion.
RETRYABLE = {500, 502, 503, 504}


class GeminiClient(LLMClient):
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float = 30.0,
        max_retries: int = 2,
        max_chars: int = 8000,
        client: httpx.Client | None = None,
        backoff: float = 1.0,
    ):
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY is required for GeminiClient"
            )

        self._api_key = api_key
        self.model = model
        self._max_retries = max_retries
        self._max_chars = max_chars
        self._backoff = backoff

        self._client = client or httpx.Client(
            timeout=timeout
        )

    def _generate(
        self,
        system: str,
        user: str,
        json_mode: bool,
    ) -> str:

        body: dict = {
            "systemInstruction": {
                "parts": [
                    {
                        "text": system
                    }
                ]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": user
                        }
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
            },
        }

        if json_mode:
            body["generationConfig"]["responseMimeType"] = (
                "application/json"
            )

        url = f"{BASE_URL}/{self.model}:generateContent"

        headers = {
            "x-goog-api-key": self._api_key,
            "Content-Type": "application/json",
        }

        last_err: Exception | None = None

        for attempt in range(self._max_retries + 1):

            try:
                logger.info(
                    f"Sending request to Gemini | "
                    f"model={self.model} | "
                    f"attempt={attempt + 1}/"
                    f"{self._max_retries + 1} | "
                    f"json_mode={json_mode}"
                )

                resp = self._client.post(
                    url,
                    headers=headers,
                    json=body,
                )

            except httpx.TimeoutException as exc:

                last_err = LLMError(
                    f"Gemini timeout: "
                    f"{type(exc).__name__}: {exc}"
                )

                logger.exception(
                    f"Gemini request timed out | "
                    f"attempt={attempt + 1} | "
                    f"model={self.model}"
                )

            except httpx.HTTPError as exc:

                last_err = LLMError(
                    f"Gemini network error: "
                    f"{type(exc).__name__}: {exc}"
                )

                logger.exception(
                    f"Gemini network error | "
                    f"attempt={attempt + 1} | "
                    f"model={self.model}"
                )

            else:

                # ==================================================
                # SUCCESS
                # ==================================================

                if resp.status_code == 200:

                    logger.info(
                        f"Gemini request successful | "
                        f"HTTP 200 | "
                        f"model={self.model} | "
                        f"attempt={attempt + 1}"
                    )

                    try:
                        return self._extract_text(
                            resp.json()
                        )

                    except Exception:

                        logger.exception(
                            "Gemini response parsing failed"
                        )

                        raise

                # ==================================================
                # 429 QUOTA / RATE LIMIT
                # ==================================================

                if resp.status_code == 429:

                    response_text = resp.text[:3000]

                    retry_after = resp.headers.get(
                        "Retry-After"
                    )

                    # IMPORTANT:
                    # Put the real Google response directly
                    # into the terminal log.
                    logger.error(
                        "GEMINI 429 ERROR | "
                        f"HTTP 429 | "
                        f"model={self.model} | "
                        f"attempt={attempt + 1} | "
                        f"Retry-After={retry_after} | "
                        f"Google response={response_text}"
                    )

                    if retry_after:

                        error_message = (
                            "Gemini quota/rate limit exceeded "
                            f"(HTTP 429). "
                            f"Retry after {retry_after} seconds. "
                            f"Google response: {response_text}"
                        )

                    else:

                        error_message = (
                            "Gemini quota/rate limit exceeded "
                            "(HTTP 429). "
                            f"Google response: {response_text}"
                        )

                    last_err = LLMError(
                        error_message
                    )

                    # DO NOT blindly retry 429.
                    break

                # ==================================================
                # OTHER API ERRORS
                # ==================================================

                response_text = resp.text[:3000]

                last_err = LLMError(
                    f"Gemini API error: "
                    f"HTTP {resp.status_code} - "
                    f"{response_text}"
                )

                logger.error(
                    "GEMINI API ERROR | "
                    f"HTTP {resp.status_code} | "
                    f"model={self.model} | "
                    f"attempt={attempt + 1} | "
                    f"Google response={response_text}"
                )

                # Retry only temporary server errors.
                if resp.status_code not in RETRYABLE:
                    break

            # ==================================================
            # RETRY TEMPORARY SERVER ERRORS
            # ==================================================

            if attempt < self._max_retries:

                sleep_time = self._backoff * (
                    2 ** attempt
                )

                logger.warning(
                    f"Gemini request failed; retrying | "
                    f"attempt={attempt + 1} | "
                    f"sleep={sleep_time}s | "
                    f"error={last_err}"
                )

                time.sleep(sleep_time)

        # ==================================================
        # PERMANENT FAILURE
        # ==================================================

        logger.error(
            f"Gemini request permanently failed | "
            f"model={self.model} | "
            f"error={last_err}"
        )

        raise last_err or LLMError(
            "Gemini request failed"
        )

    @staticmethod
    def _extract_text(data: dict) -> str:

        try:

            candidates = data.get(
                "candidates",
                []
            )

            if not candidates:
                raise LLMOutputError(
                    "Gemini returned no candidates"
                )

            content = candidates[0].get(
                "content"
            )

            if not content:
                raise LLMOutputError(
                    "Gemini returned no content"
                )

            parts = content.get(
                "parts",
                []
            )

            text = "".join(
                p.get("text", "")
                for p in parts
                if isinstance(p, dict)
            ).strip()

            if not text:

                finish_reason = candidates[0].get(
                    "finishReason"
                )

                raise LLMOutputError(
                    "Gemini returned empty text. "
                    f"Finish reason: {finish_reason}"
                )

            return text

        except LLMOutputError:
            raise

        except (
            KeyError,
            IndexError,
            TypeError,
        ) as exc:

            raise LLMOutputError(
                "Gemini returned no usable candidate "
                "(possibly blocked)"
            ) from exc

    @staticmethod
    def _parse_json(text: str) -> dict:

        text = re.sub(
            r"^```(?:json)?\s*|\s*```$",
            "",
            text.strip(),
        )

        try:

            obj = json.loads(text)

        except json.JSONDecodeError as exc:

            logger.error(
                f"Gemini returned invalid JSON | "
                f"response={text[:2000]}"
            )

            raise LLMOutputError(
                "Gemini returned invalid JSON"
            ) from exc

        if not isinstance(obj, dict):

            raise LLMOutputError(
                "Gemini JSON output is not an object"
            )

        return obj

    def analyze_email(
        self,
        payload: dict,
        preferences: dict,
        today: date,
    ) -> EmailAnalysisResult:

        user = prompts.build_analysis_user_prompt(
            payload,
            preferences,
            today.isoformat(),
            self._max_chars,
        )

        raw = self._generate(
            prompts.ANALYSIS_SYSTEM_PROMPT,
            user,
            json_mode=True,
        )

        try:

            return EmailAnalysisResult.model_validate(
                self._parse_json(raw)
            )

        except ValidationError as exc:

            logger.error(
                "Gemini output failed schema validation | "
                f"error={exc} | "
                f"response={raw[:2000]}"
            )

            raise LLMOutputError(
                "Gemini output failed schema validation"
            ) from exc

    def draft_reply(
        self,
        payload: dict,
        analysis: dict,
        instructions: str | None = None,
    ) -> str:

        user = prompts.build_reply_user_prompt(
            payload,
            analysis,
            instructions,
            self._max_chars,
        )

        text = self._generate(
            prompts.REPLY_SYSTEM_PROMPT,
            user,
            json_mode=False,
        )

        if not text:

            raise LLMOutputError(
                "Gemini returned an empty draft"
            )

        return text