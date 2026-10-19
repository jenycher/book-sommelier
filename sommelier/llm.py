"""Обёртка над текстовым API Pollinations.

Работает двумя способами:
- без ключа: https://text.pollinations.ai/openai — лимит 1 запрос в 30 секунд
  на IP, один бесплатный слой моделей; выдерживается автоматически (pacing);
- с ключом: переменная окружения POLLINATIONS_API_KEY — endpoint
  https://gen.pollinations.ai/v1/chat/completions, без лимита частоты.

Модели могут оборачивать JSON в markdown-ограждение — extract_json это снимает.
"""
import json
import os
import re
import threading
import time

import requests

import config

_LAST_CALL = 0.0
_FREE_WINDOW = 32.0  # секунд между запросами в бесплатном режиме (лимит — 30)
_free_lock = threading.Lock()


class LLMError(Exception):
    """Модель недоступна или вернула невалидный ответ."""


def extract_json(text):
    """Достаёт первый JSON-объект из ответа модели (снимает ```-ограждения)."""
    cleaned = re.sub(r"```(?:json)?", "", text or "")
    start = cleaned.find("{")
    if start == -1:
        raise json.JSONDecodeError("в ответе модели нет JSON-объекта", text or "", 0)
    obj, _ = json.JSONDecoder().raw_decode(cleaned[start:])
    return obj


def _chat(messages, force_schema=True):
    global _LAST_CALL
    api_key = os.environ.get("POLLINATIONS_API_KEY")
    if api_key:
        url = "https://gen.pollinations.ai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}"}
    else:
        url = "https://text.pollinations.ai/openai"
        headers = {}
        # бесплатный режим: не чаще одного запроса за окно
        with _free_lock:
            wait = _FREE_WINDOW - (time.monotonic() - _LAST_CALL)
            if wait > 0:
                time.sleep(wait)
            _LAST_CALL = time.monotonic()

    payload = {
        "model": config.MODEL,
        "messages": messages,
        "max_tokens": config.LLM_MAX_TOKENS,
        # бесплатная модель gpt-oss-20b «размышляет» за те же токены,
        # что и ответ: low оставляет их на полезный вывод
        "reasoning_effort": "low",
    }
    if force_schema:
        # иначе модель любит придумывать свои ключи вместо заявленной
        # схемы — json_object её дисциплинирует; для шага вкуса, наоборот,
        # оказался надёжнее свободный JSON
        payload["response_format"] = {"type": "json_object"}

    response = requests.post(url, headers=headers, json=payload,
                             timeout=config.LLM_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    content = data["choices"][0]["message"].get("content")
    if not content:
        raise json.JSONDecodeError("модель вернула пустой ответ", "", 0)
    return content


def chat_json(messages, force_schema=True):
    """Запрос к модели, ответ парсится как JSON. Один ретрай при сбое."""
    last_error = None
    for _ in range(config.LLM_RETRIES + 1):
        try:
            return extract_json(_chat(messages, force_schema))
        except (requests.RequestException, json.JSONDecodeError, KeyError) as error:
            last_error = error
    raise LLMError(f"модель не ответила корректно: {last_error}")