# How the agent calls Sarvam, and how those calls are traced and priced

Answers [issue #8](https://github.com/Samarthra/fraud_det/issues/8). Checked 2026-10-31 against live Sarvam and Langfuse Cloud (US), using synthetic data only.

## Recommendation

- **Client:** `ChatOpenAI` with `base_url=https://api.sarvam.ai/v2`. Not `ChatSarvam`, which only calls `/v1`.
- **Proxy:** drop LiteLLM. It can carry v2, but with one provider it adds a Docker service and a failure point and returns nothing the app uses. Keep the base URL configurable.
- **Cost:** Langfuse has no Sarvam price. Create one custom model definition using `pricingTiers` with four price keys, before the first real run. A flat input/output price undercounted by 89%.
- **Reasoning:** set `reasoning_effort="none"` on every stage. This is the biggest single finding. With it, a full Investigation took 6s and $0.0005, against about 30s and $0.0027 with default reasoning. It also removes the cause of the "empty JSON" result.
- **Synthesis:** use `with_structured_output(Case, method="function_calling", include_raw=True)`, which forces a tool call. 17 of 17 valid at 1.5-2.9s. Do not use `response_format`.

"Tested" below means a real call to Sarvam or Langfuse Cloud: about 100 Sarvam calls in total, an estimated ₹5 of credit. Anything else is under [Not verified](#not-verified).

## Pins

Tested on Python 3.13: `langgraph==1.2.19 langchain==1.4.7 langchain-core==1.7.3 langchain-openai==1.7.3 openai==2.54.0 langfuse==5.1.0 pydantic==2.14.2`

Drop `langchain-anthropic` and `anthropic` from issue 2's pins, and `ANTHROPIC_OPEN_TELEMETRY`. Everything else in issue 2's one-trace design stands.

## Setup

```python
import os
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="sarvam-105b",
    base_url=os.environ.get("SARVAM_BASE_URL", "https://api.sarvam.ai/v2"),
    api_key=os.environ["SARVAM_API_KEY"],
    reasoning_effort="none",  # see "Reasoning" below
    max_tokens=1500,          # counts reasoning tokens; also caps runaway output
    timeout=45,
    max_retries=2,            # transport retries, separate from the Synthesis retry
    stream_usage=True,        # off by default with a custom base_url
)
synthesis = llm.with_structured_output(Case, method="function_calling", include_raw=True)
```

`Case` is a Pydantic model. Tracing is unchanged from issue 2: one `CallbackHandler(trace_context={"trace_id": Langfuse.create_trace_id(seed=investigation_id)})` per invoke, `Langfuse(mask_otel_spans=...)` first, then `langfuse.flush()`.

## 1. Client

Three-tool scenario through LangGraph `create_agent`: one tool call, then two parallel calls, then a final summary.

| Client | Endpoint | Result (tested) | Verdict |
|---|---|---|---|
| `ChatOpenAI` | v2 | 3 of 3 loops with default reasoning at 3.1-3.6s; 2 of 2 with `none` at 3.4s | **Use** |
| `ChatOpenAI` via proxy | v2 | 2 of 2 at 3.5-4.0s | Works, not needed |
| `ChatLiteLLM` | v2 | 1 of 1 at 5.4s | Works. Replays reasoning, so input grew 413 to 484 on turn two. Extra dependency |
| `ChatSarvam` 0.1.2 | v1 only | 1 of 1 at 3.5s | Avoid |

- [`ChatSarvam`](https://docs.sarvam.ai/api/integration/langchain.md) is Sarvam's official package, but it calls `client.chat.completions`, and the `sarvamai` SDK maps that to `v1/chat/completions`. `base_url` changes the host, not the path. It also drops cached-token counts, so traced cost would be overstated.
- Sarvam [documents `Authorization: Bearer`](https://docs.sarvam.ai/api/token-factory/chat-completions.md) for OpenAI-compatible tooling. Tested.
- `ChatOpenAI` does not replay `reasoning_content`. This caused no error on any turn.
- `ChatSarvam`'s single v1 success differs from issue 3's single v1 miss. That is two samples in total, so v1 tool reliability stays unknown. We no longer need it.

## 2. LiteLLM Proxy

**It can carry v2. Remove it anyway.**

Tested on `litellm/litellm:v1.106.6`, port 4100:

| Check | Result |
|---|---|
| `openai/sarvam-105b` or `sarvam/sarvam-105b` with `api_base: https://api.sarvam.ai/v2` | Both hit v2 |
| `sarvam/sarvam-105b` with no `api_base` | Silently hits **v1** ([built-in default](https://github.com/BerriAI/litellm/blob/main/litellm/llms/openai_like/providers.json)) |
| Tool loop, `json_schema`, forced tool with `reasoning_effort: "none"`, streaming usage | All pass through |
| `x-litellm-response-cost` | Absent. Its [price list](https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json) has only `sarvam/sarvam-m`, at 0 |
| Overhead | 844ms on the first request, about 5ms after |

Why it goes:

- Its usual value is routing between providers. There is one provider and no fallback.
- It no longer does cost or tracing: only the app emits, and it has no price.
- `max_retries` on the client already covers 429 and 503.
- It costs Docker, a master key, a port on a machine where 4000 is taken, and setup time on an 8-hour day.
- Sarvam is a plain HTTPS call, so the proxy is a failure point with no matching protection.

The "bypass" decision still holds and becomes simpler: `SARVAM_BASE_URL` is the one setting. To bring the proxy back, set `SARVAM_BASE_URL` to `http://localhost:4100/v1` and change the key. Keep `SARVAM_API_KEY` passed explicitly, since `.env` also holds a dead `OPENAI_API_KEY`.

## 3. Langfuse cost

Langfuse has [no built-in Sarvam price](https://github.com/langfuse/langfuse/blob/main/worker/src/constants/default-model-prices.json). Tested: 191 models in the project's list, no Sarvam entry, and with no definition cost came back empty while usage was recorded.

**Price:** ₹15 input, ₹5 cached input, ₹60 output per 1M tokens, [excluding GST, with reasoning billed as output](https://docs.sarvam.ai/api/getting-started/pricing.md). Sarvam's [pricing page](https://www.sarvam.ai/api-pricing) agrees. Search-engine copies showed ₹29.28/₹10.98/₹73.2 and ₹4/₹2.5/₹16; both live pages disagree with those, so ignore them.

**Currency:** Langfuse prices are [defined in USD](https://github.com/langfuse/langfuse-python/blob/main/langfuse/api/models/types/create_model_request.py). Converted at ₹94.95 per USD ([ECB-based rate, 2026-10-30](https://api.frankfurter.dev/v1/latest?base=USD&symbols=INR)), which is a fixed assumption.

**Why four keys:** the [`CallbackHandler`](https://github.com/langfuse/langfuse-python/blob/main/langfuse/langchain/CallbackHandler.py) subtracts cached tokens from `input` and reasoning tokens from `output`, then reports each under its own key. [Usage keys must match prices exactly](https://langfuse.com/docs/observability/features/token-and-cost-tracking), so anything unpriced costs 0.

| Definition (tested on same scenario, default reasoning) | Langfuse cost | From usage at list price |
|---|---|---|
| None | empty | $0.00265 |
| Flat `inputPrice` / `outputPrice` | $0.00028 | $0.00249 (**89% under**) |
| `pricingTiers` with four keys | $0.002654397 | $0.002654397 |
| Same, `stream_mode="messages"` | $0.002760084 | $0.002760084 |

Run this once per project, **before the first real run**. Costs are [set at ingestion and are not retroactive](https://langfuse.com/docs/observability/features/token-and-cost-tracking).

```bash
curl -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" -H 'Content-Type: application/json' \
  "$LANGFUSE_BASE_URL/api/public/models" -d '{
  "modelName": "sarvam-105b", "matchPattern": "(?i)^sarvam-105b$", "unit": "TOKENS",
  "pricingTiers": [{"name": "Standard", "isDefault": true, "priority": 0, "conditions": [],
    "prices": {"input": 1.579779e-7, "input_cache_read": 5.26593e-8,
               "output": 6.319115e-7, "output_reasoning": 6.319115e-7}}]}'
```

The test definition was deleted afterwards, so **this step still has to be run**. Costs already stored stayed intact after deletion (tested).

**One trace, tested end to end** with Triage, the Evidence subgraph, Synthesis and a Follow-up: 1 trace ID, 1 session, 29 observations (6 generations, 3 tools, 20 chains), account IDs masked, all generations matched to the definition. It took 5.9s plus 0.3s for the Follow-up and cost **$0.000505 (about ₹0.05)**. The Follow-up joined the same trace by using a second handler with the same seed.

The ₹100 signup credit would cover roughly 2,000 Investigations at this rate. [Issue 3](https://github.com/Samarthra/fraud_det/issues/3) has not confirmed the actual balance.

**Reading traces back:** `GET /api/public/traces` and `/traces/{id}` are [being removed on 2026-11-16](https://langfuse.com/docs/api-and-data-platform/features/public-api#v2). Today they already returned 410 and 429 (limit of 5). Use `GET /api/public/v2/observations` with `traceId`, `fromStartTime`, `toStartTime` and `fields=core,basic,time,io,metadata,model,usage`, as tested. For Governance trace links, `langfuse.get_trace_url(trace_id=...)` needs no read API (tested). Data was readable within about 45s.

## 4. Reasoning and Synthesis

**The "empty JSON" cause.** `sarvam-105b` reasons at length on calls without tools. Reasoning counts against `max_tokens`, which [defaults to 2048 on v2](https://docs.sarvam.ai/api-reference/chat/chat-completions-v2.md). The call ends with `finish_reason: "length"`, 2047 reasoning tokens and no content. This also hit a one-line Triage call. Tool-loop turns stay small, which is why issue 3 saw about 1s for tools and 13-18s for JSON.

**Turning it off.**

| Setting | Tested result |
|---|---|
| v2, omitted or `null` | Reasoning stays on |
| v2, `"none"` | **Reasoning tokens 0** on every call. Sarvam's [v2 reference](https://docs.sarvam.ai/api-reference/chat/chat-completions-v2.md) does not list `sarvam-105b` for this value, so this is observed, not promised |
| v2, `"low"` | Worse in its one run: 5999 reasoning tokens, empty |
| v1, `"none"` | 400 |
| v1, `null` | Reasoning off, as [documented](https://docs.sarvam.ai/api/token-factory/chat-completions.md) |

**Validity.** Case schema with enums and nested claims, 5-record Evidence pack. "Valid" means parses, matches the schema, evidence IDs exist, amounts match.

| Request (v2 unless noted) | `max_tokens` | Valid | Latency | Failures |
|---|---|---|---|---|
| **Forced tool, `none`, LangChain** | 1500 | **12 of 12** | **1.5-2.9s** | None |
| **Forced tool, `none`, raw HTTP** | 1500 | **5 of 5** | **2.2-2.7s** | None |
| Forced tool, default reasoning | 6000 | 3 of 3 | 22-29s | None, but 2.5-3k tokens |
| `json_schema` strict, `none` | 1500-6000 | 2 of 5 | 2.4-53s | 3 runaways, 2 confirmed as endless whitespace |
| `json_schema` strict, default | 2048 | 0 of 3 | 15-16s | All empty |
| `json_schema` strict, default | 6000 | 1 of 2 | 22-44s | One runaway of `000...` |
| `json_schema` strict, `low` | 6000 | 0 of 1 | 54s | Empty |
| `json_object`, `none` | 1500 | 0 of 2 | 2.2-2.4s | Valid JSON, wrong shape |
| v1 `json_schema`, `null` | 3000 | 3 of 4 | 2.0-3.8s | One failed the amount check (output not inspected) |

Sarvam [documents strict `json_schema` as constraining output](https://docs.sarvam.ai/api/token-factory/chat-completions.md), but the runaways show it is not enforced on v2. Forced tool calling is Sarvam's [documented alternative](https://docs.sarvam.ai/api/token-factory/chat-completions.md).

**The 12 LangChain runs** are 6 unguided, 3 guided false-positive, 2 retries and 1 end-to-end.

**Handling bad output, within one retry:**

```python
result = synthesis.invoke(messages)
raw, case = result["raw"], result["parsed"]
errors = verify(case, evidence) if case else [f"bad output: {result['parsing_error']}"]
if raw.response_metadata.get("finish_reason") == "length":
    errors.append("output truncated")
```

1. Any error from parsing, truncation or Verification takes the one retry. Send the draft and the errors back as a message, as Verification would.
2. On a second failure, save the Case as Unverified with the errors shown. When neither attempt parsed, the Case still exists with no draft claims, because every Investigation produces one Case.
3. Check Pydantic and `finish_reason` in code. `method="function_calling"` keeps the schema out of the failure path but does not prove it.

Tested: a seeded draft with a wrong amount and an unknown evidence ID was corrected in 2 of 2 retries at 2.5-2.9s. Worst case is about 11s per attempt, the time to hit the 1500-token cap.

**Fallback** if Sarvam starts rejecting `"none"`: omit `reasoning_effort`, set `max_tokens=6000`, keep the forced tool, and accept 22-29s. Tested 3 of 3.

**Decision quality.** Validity is not correctness. On a benign fixture (a large rent payment on an old device to a long-standing payee), `none` said `suspicious` 2 of 3 times. Default reasoning did no better, also 1 of 3 correct at 12-25s, so reasoning is not the fix. Adding explicit guidance to the system prompt gave 3 of 3 `not_suspicious` at 1.5-1.8s. That guidance closely mirrors the fixture, so treat it as a direction for the dismissed false-positive scenario, not a measured rate. Verification cannot catch this, because the facts all match.

## Pitfalls

1. **Sarvam's Limits table is v1 only**, as its [own note says](https://docs.sarvam.ai/api/token-factory/chat-completions.md). `max_tokens=6000` was accepted on v2.
2. **`recursion_limit`:** tests used 14, about two supersteps per tool step for the 6-step cap. The loop finished in 3 steps, so hitting the cap was not tested. Catch `GraphRecursionError` and go to Synthesis with the Evidence so far.
3. **Generations are named `ChatOpenAI`** in Langfuse. Cosmetic.
4. **Replies can start with `\n`.** Strip before display.
5. **Rate limit** is [60 requests a minute on Pay as you go](https://docs.sarvam.ai/api/getting-started/pricing.md). An Investigation uses about 6 calls. Empty credit returns [402, which no retry fixes](https://docs.sarvam.ai/api/getting-started/pricing.md); Replay is the fallback.

## Not verified

- **`reasoning_effort="none"` on v2 for this model is undocumented.** It worked on every call today and may change. Run one Investigation on demo morning.
- **Sample size.** 17 of 17 is two fixtures of at most 5 records, so a failure rate up to about 16% is not ruled out. Larger Evidence packs were not tested.
- **Correct verdicts.** Not measured beyond the small fixture above. That is eval work ([issue 6](https://github.com/Samarthra/fraud_det/issues/6)).
- **Actual billing.** Costs are computed from list prices. No Sarvam invoice or balance was checked, and GST and exchange-rate movement are excluded.
- **Credit balance**, and the 402, 429 and 503 paths. None occurred.
- **Concurrency.** Tests ran at most 3 parallel calls.
- **Langfuse UI.** Everything was read through the API. The trace name was not confirmed, because the only endpoint exposing it returned 410.
- **Real Case schema.** Tests used a stand-in; [issue 4](https://github.com/Samarthra/fraud_det/issues/4) defines the real one. Check its Pydantic JSON Schema works as tool parameters.
- **Streaming Synthesis.** Streaming was tested for the agent and through the proxy, not with a forced tool.
