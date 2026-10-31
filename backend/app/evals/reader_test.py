"""Does the LLM read enrolment text better than a phrase match? From backend/app: python -m evals.reader_test"""

import json
from pathlib import Path

from dotenv import load_dotenv

from agent.graph import read_with_model
from demo.generator import NEGATED, PARAPHRASED

from .sweep import phrase_read

OUT = Path(__file__).parent / "results" / "reader.json"
PASS_RATE = 0.9


def score(read) -> dict:
    rows = [(d, True) for d in PARAPHRASED] + [(d, False) for d in NEGATED]
    correct, misses = 0, []
    for n, (details, expected) in enumerate(rows):
        events = [{"event_id": f"EVT-T{n}", "details": details}]
        found = bool(read(events))
        correct += found == expected
        if found != expected:
            misses.append({"details": details, "expected": expected})
    return {"correct": correct, "total": len(rows), "rate": round(correct / len(rows), 3), "misses": misses}


def main() -> None:
    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    llm = read_with_model()
    problems: list[str] = []

    def read_llm(events):
        kept, issues = llm(events, {})
        problems.extend(issues)
        return kept

    phrase, model = score(phrase_read), score(read_llm)
    result = {
        "phrase_match": phrase,
        "llm": model,
        "problems": problems,
        "llm_stays": model["rate"] >= PASS_RATE and model["rate"] > phrase["rate"],
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "phrase_match"}, indent=2, ensure_ascii=False))
    print("phrase", phrase["correct"], "of", phrase["total"])


if __name__ == "__main__":
    main()
