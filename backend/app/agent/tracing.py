"""One Investigation, one Langfuse trace. Only the app emits."""

import os
import re
from functools import lru_cache
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
from langfuse.types import MaskOtelSpansResult, OtelSpanPatch

VALUES = re.compile(r"ACC-[A-Z0-9-]+|\b\d{13,19}\b")
FIELDS = re.compile(r'(\\*"(?:card_number|iban|email|phone)\\*"\s*:\s*\\*")[^"\\]*')


def scrub(text: str) -> str:
    return FIELDS.sub(r"\1[REDACTED]", VALUES.sub("[REDACTED]", text))


def mask_otel_spans(*, params):
    patches = {}
    for key, span in params.spans.items():
        changed = {
            k: scrub(v)
            for k, v in span.attributes.items()
            if isinstance(v, str) and scrub(v) != v
        }
        if changed:
            patches[key] = OtelSpanPatch(set_attributes=changed)
    return MaskOtelSpansResult(span_patches=patches)


def enabled() -> bool:
    return bool(os.environ.get("LANGFUSE_SECRET_KEY"))


@lru_cache
def client() -> Langfuse:
    return Langfuse(mask_otel_spans=mask_otel_spans)


class CallCounter(BaseCallbackHandler):
    """Evals report model calls, because real cost can't be read back."""

    def __init__(self) -> None:
        self.calls = 0

    def on_chat_model_start(self, *args: Any, **kwargs: Any) -> None:
        self.calls += 1


counter = CallCounter()


def trace_config(investigation_id: str) -> dict[str, Any]:
    """A fresh handler per invoke. The seeded ID keeps Follow-ups in the same trace."""
    if not enabled():
        return {"callbacks": [counter]}
    client()
    handler = CallbackHandler(
        trace_context={"trace_id": Langfuse.create_trace_id(seed=investigation_id)}
    )
    return {
        "callbacks": [handler, counter],
        "metadata": {
            "langfuse_session_id": investigation_id,
            "langfuse_trace_name": "investigation",
            "langfuse_tags": ["fraud"],
        },
    }


def trace_url(investigation_id: str) -> str | None:
    if not enabled():
        return None
    return client().get_trace_url(trace_id=Langfuse.create_trace_id(seed=investigation_id))


def score(investigation_id: str, passed: bool, group: str) -> None:
    if enabled():
        client().create_score(
            trace_id=Langfuse.create_trace_id(seed=investigation_id),
            name="eval_passed",
            value=float(passed),
            comment=group,
        )


def flush() -> None:
    if enabled():
        client().flush()
