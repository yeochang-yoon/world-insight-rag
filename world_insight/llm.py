import json
import re

from openai import OpenAI

from .errors import ServiceError


def parse_object(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        raise ServiceError(
            "AI 응답 형식이 올바르지 않습니다. 다시 시도해 주세요."
        ) from None
    if not isinstance(value, dict):
        raise ServiceError("AI 응답은 JSON 객체여야 합니다.")
    return value


class ResponsesLLM:
    def __init__(self, settings):
        if not settings.api_key:
            raise ServiceError(
                "API 키가 없습니다. .env의 OPENAI_API_KEY를 설정해 주세요."
            )
        self.model = settings.model
        self.client = OpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout=settings.timeout,
            max_retries=1,
        )

    def json(self, system, data):
        try:
            response = self.client.responses.create(
                model=self.model,
                instructions=system,
                input=json.dumps(data, ensure_ascii=False),
                store=False,
            )
            raw = response.output_text
        except Exception:
            raise ServiceError(
                "LLM 호출에 실패했습니다. API 인증·모델 지원·네트워크 상태를 확인해 주세요."
            ) from None
        return parse_object(raw)
