import os

from langchain_openai import ChatOpenAI

from contracts import FollowUpDraft, OtpDraft, ReportDraft


def chat_model() -> ChatOpenAI:
    return ChatOpenAI(
        model="sarvam-105b",
        base_url=os.environ.get("SARVAM_BASE_URL", "https://api.sarvam.ai/v2"),
        api_key=os.environ["SARVAM_API_KEY"],
        reasoning_effort="none",
        max_tokens=1500,
        timeout=45,
        max_retries=2,
        stream_usage=True,
    )


def report_model(llm: ChatOpenAI):
    return llm.with_structured_output(ReportDraft, method="function_calling", include_raw=True)


def otp_model(llm: ChatOpenAI):
    return llm.with_structured_output(OtpDraft, method="function_calling", include_raw=True)


def follow_up_model(llm: ChatOpenAI):
    return llm.with_structured_output(FollowUpDraft, method="function_calling", include_raw=True)
