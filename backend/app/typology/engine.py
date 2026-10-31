"""A small forward-chaining evaluator. Proofs and missing facts come from how it runs.

Rules run once, in file order, and may use only facts or the heads of earlier rules. A head can't
gain a rule once something has read it, which rules out recursion and negation through a cycle, so
there is nothing to stratify.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from string import Formatter
from typing import Any, Iterator

import yaml

from correlation.consolidate import inr

RULES_FILE = Path(__file__).resolve().parents[1] / "detection" / "typologies.yaml"
FACT_ARITY = {
    "event": 5, "failed_login": 3, "failed_then_success": 4, "payment": 6, "first_payment": 1,
    "new_device": 2, "payer_count": 2, "only_payer": 2, "payout": 4, "claim": 3,
    "shared_claim": 5, "otp_verified": 2,
}
TEST_ARITY = {"within": 3, "gap_at_least": 3, "near": 3, "at_least": 2, "share_at_least": 3,
              "in_window": 1}
RULE_KEYS = {"id", "head", "when", "typology", "name", "report_near", "near_needs_first"}
ENTRY_KEYS = {"fact", "test", "absent", "say", "missing"}


class RuleError(ValueError):
    """A rule file that can't be trusted. Refused at load, never half-applied."""


@dataclass(frozen=True)
class Source:
    kind: str
    ref: str


@dataclass
class Fact:
    pred: str
    args: tuple
    source: Source | None = None
    rule: "Rule | None" = None
    premises: list = field(default_factory=list)
    alternatives: list = field(default_factory=list)  # other ways the same conclusion held


@dataclass
class Entry:
    kind: str
    atom: list
    items: list["Entry"] = field(default_factory=list)
    say: str | None = None
    missing: str | None = None


@dataclass
class Rule:
    id: str
    head: list
    when: list[Entry]
    typology: str | None = None
    name: str | None = None
    report_near: bool = False
    near_needs_first: bool = False


def _vars(atom: list) -> set[str]:
    return {t for t in atom if isinstance(t, str) and t.startswith("$")}


def _entry(raw: dict, where: str, known: dict[str, int]) -> Entry:
    if not isinstance(raw, dict) or set(raw) - ENTRY_KEYS:
        raise RuleError(f"{where}: unknown keys in {raw!r}.")
    kinds = [k for k in ("fact", "test", "absent") if k in raw]
    if len(kinds) != 1:
        raise RuleError(f"{where}: an entry needs exactly one of fact, test or absent.")
    kind = kinds[0]
    if kind == "absent":
        items = [_entry(i, where, known) for i in raw["absent"]]
        if not any(i.kind == "fact" for i in items):
            raise RuleError(f"{where}: absent needs a fact.")
        if any(i.kind == "absent" for i in items):
            raise RuleError(f"{where}: absent can't hold another absent.")
        return Entry("absent", [], items, raw.get("say"), raw.get("missing"))
    atom = raw[kind]
    if not isinstance(atom, list) or not atom or not all(isinstance(t, (str, int, float)) for t in atom):
        raise RuleError(f"{where}: bad {kind} {atom!r}.")
    table = known if kind == "fact" else TEST_ARITY
    if atom[0] not in table:
        raise RuleError(f"{where}: unknown {kind} {atom[0]!r}. A rule may use only earlier heads.")
    if len(atom) - 1 != table[atom[0]]:
        raise RuleError(f"{where}: {atom[0]} takes {table[atom[0]]} values.")
    return Entry(kind, atom, [], raw.get("say"), raw.get("missing"))


def _check_test(rule_id: str, entry: Entry, bound: set[str]) -> None:
    terms = entry.atom[1:]
    if any(isinstance(t, str) and not t.startswith("$") for t in terms):
        raise RuleError(f"{rule_id}: {entry.atom[0]} takes values and numbers only.")
    if _vars(terms) - bound:
        raise RuleError(f"{rule_id}: {entry.atom[0]} uses a value not yet bound.")


def _check_bindings(rule_id: str, when: list[Entry]) -> set[str]:
    """Every value is bound before it's used. Returns those the body binds."""
    bound: set[str] = set()
    for n, entry in enumerate(when):
        if entry.kind == "fact":
            bound |= _vars(entry.atom)
        elif entry.kind == "test":
            _check_test(rule_id, entry, bound)
        else:
            inner = set(bound)
            for item in entry.items:
                if item.kind == "fact":
                    inner |= _vars(item.atom)
                else:
                    _check_test(rule_id, item, inner)
            later = {v for e in when[n + 1:] if e.kind == "fact" for v in _vars(e.atom)}
            if (inner - bound) & later:
                raise RuleError(f"{rule_id}: absent runs before a value it shares is bound.")
    for entry in when:
        if entry.say and {f"${f}" for _, f, _, _ in Formatter().parse(entry.say) if f} - bound:
            raise RuleError(f"{rule_id}: a say line uses a value the body never binds.")
    return bound


def _reads(when: list[Entry]) -> set[str]:
    return {e.atom[0] for e in when if e.kind == "fact"} | {
        i.atom[0] for e in when if e.kind == "absent" for i in e.items if i.kind == "fact"
    }


def parse_rules(raw: Any) -> list[Rule]:
    if not isinstance(raw, list):
        raise RuleError("The rule file must be a list.")
    known = dict(FACT_ARITY)
    rules: list[Rule] = []
    seen: set[str] = set()
    read: set[str] = set()
    for item in raw:
        if not isinstance(item, dict) or set(item) - RULE_KEYS or {"id", "head", "when"} - set(item):
            raise RuleError(f"Bad rule {item!r}.")
        rule_id = item["id"]
        if rule_id in seen:
            raise RuleError(f"Duplicate rule {rule_id}.")
        seen.add(rule_id)
        if item.get("typology") not in (None, "fraud", "legitimate"):
            raise RuleError(f"{rule_id}: typology must be fraud or legitimate.")
        if item.get("typology") and not item.get("name"):
            raise RuleError(f"{rule_id}: a Typology needs a name.")
        if not isinstance(item["when"], list):
            raise RuleError(f"{rule_id}: when must be a list.")
        when = [_entry(e, rule_id, known) for e in item["when"]]
        bound = _check_bindings(rule_id, when)
        head = item["head"]
        if not isinstance(head, list) or not head or not isinstance(head[0], str):
            raise RuleError(f"{rule_id}: bad head {head!r}.")
        if head[0] in FACT_ARITY:
            raise RuleError(f"{rule_id}: {head[0]} is an input fact, so a rule can't conclude it.")
        read |= _reads(when)
        if head[0] in read:
            raise RuleError(f"{rule_id}: {head[0]} was already read, so this would be recursion or missed.")
        if "_" in head:
            raise RuleError(f"{rule_id}: a head can't hold _.")
        if _vars(head) - bound:
            raise RuleError(f"{rule_id}: head uses a value the body never binds.")
        if item.get("typology") and "$t" not in bound:
            raise RuleError(f"{rule_id}: a Typology must bind $t, the time it held.")
        if known.get(head[0], len(head) - 1) != len(head) - 1:
            raise RuleError(f"{rule_id}: {head[0]} has a different size elsewhere.")
        known[head[0]] = len(head) - 1
        rules.append(Rule(rule_id, head, when, item.get("typology"), item.get("name"),
                          bool(item.get("report_near")), bool(item.get("near_needs_first"))))
    return rules


def load_rules(path: Path = RULES_FILE) -> list[Rule]:
    return parse_rules(yaml.safe_load(path.read_text()))


def _test(atom: list, b: dict, window: tuple[int, int]) -> bool:
    name, *terms = atom
    x = [b.get(t, t) for t in terms]
    if name == "within":
        return 0 <= x[1] - x[0] <= x[2]
    if name == "gap_at_least":
        return x[1] - x[0] >= x[2]
    if name == "near":
        return abs(x[1] - x[0]) <= x[2]
    if name == "at_least":
        return x[0] >= x[1]
    if name == "share_at_least":
        return x[0] >= x[2] * x[1]
    return window[0] <= x[0] <= window[1]  # in_window


def _match(atom: list, fact: Fact, binding: dict) -> dict | None:
    out = dict(binding)
    for term, value in zip(atom[1:], fact.args):
        if term == "_":
            continue
        if isinstance(term, str) and term.startswith("$"):
            if term in out and out[term] != value:
                return None
            out[term] = value
        elif term != value:
            return None
    return out


def _solve(entries: list[Entry], binding: dict, index, window) -> Iterator[tuple[dict, list]]:
    if not entries:
        yield binding, []
        return
    entry, rest = entries[0], entries[1:]
    if entry.kind == "test":
        if _test(entry.atom, binding, window):
            yield from ((b, [(entry, None), *p]) for b, p in _solve(rest, binding, index, window))
    elif entry.kind == "absent":
        if next(_solve(entry.items, binding, index, window), None) is None:
            yield from ((b, [(entry, None), *p]) for b, p in _solve(rest, binding, index, window))
    else:
        for fact in index[entry.atom[0]]:
            matched = _match(entry.atom, fact, binding)
            if matched is not None:
                for b, p in _solve(rest, matched, index, window):
                    yield b, [(entry, fact), *p]


def _render(text: str, binding: dict) -> str:
    values = {k[1:]: inr(v) if "amt" in k else v for k, v in binding.items()}
    return text.format_map(values)


def evaluate(rules: list[Rule], facts: list[Fact], window: tuple[int, int]):
    """Returns every derived fact, plus the index for `nearest`."""
    index: dict[str, list[Fact]] = defaultdict(list)
    for fact in facts:
        index[fact.pred].append(fact)
    derived: list[Fact] = []
    for rule in rules:
        seen = {f.args: f for f in index[rule.head[0]]}
        for binding, premises in _solve(rule.when, {}, index, window):
            args = tuple(binding.get(t, t) for t in rule.head[1:])
            used = [(e, f, binding) for e, f in premises]
            if args in seen:
                seen[args].alternatives.append(used)
                continue
            fact = Fact(rule.head[0], args, None, rule, used)
            seen[args] = fact
            index[rule.head[0]].append(fact)
            derived.append(fact)
    return derived, index


def first_time(fact: Fact) -> int:
    """When the conclusion first held: the earliest `$t` of any way it was reached."""
    return min(premises[0][2]["$t"] for premises in [fact.premises, *fact.alternatives])


def proof_steps(fact: Fact) -> tuple[list[dict], list[Source]]:
    """The readable steps, and every source record they rest on, down to the leaves."""
    steps: dict[str, dict] = {}
    sources: list[Source] = []
    for premises in [fact.premises, *fact.alternatives]:
        for entry, premise, binding in premises:
            if premise is not None and premise.rule is not None:
                inner, cited = proof_steps(premise)
                steps.update({s["text"]: s for s in inner})
                sources += cited
                continue
            record = premise.source.ref if premise is not None and premise.source else None
            if premise is not None and premise.source:
                sources.append(premise.source)
            if entry.say:
                text = _render(entry.say, binding)
                quote = premise.args[1] if premise is not None and premise.pred == "otp_verified" else None
                steps.setdefault(text, {"text": text, "record": record, "quote": quote})
    return list(steps.values()), sources


def nearest(rule: Rule, index, window, accounts: list[str]) -> dict[str, str]:
    """For a rule one requirement short, says what's missing, by account."""
    found: dict[str, str] = {}

    def walk(entries, binding, skipped, gone, matched):
        if len(skipped) > 1:
            return
        if not entries:
            if len(skipped) == 1 and matched and "$a" in binding:
                found.setdefault(binding["$a"], skipped[0])
            return
        entry, rest = entries[0], entries[1:]
        blocked_by = _vars(entry.atom) & gone if entry.kind != "absent" else set()
        if blocked_by:  # depends on what's already missing, so it isn't a second gap
            walk(rest, binding, skipped, gone | (_vars(entry.atom) - set(binding)), matched)
        elif entry.kind == "fact":
            hits = [m for f in index[entry.atom[0]] if (m := _match(entry.atom, f, binding)) is not None]
            for hit in hits:
                walk(rest, hit, skipped, gone, matched + 1)
            if not hits and not (rule.near_needs_first and entry is rule.when[0]):
                walk(rest, binding, [*skipped, entry.missing or entry.say or entry.atom[0]],
                     gone | (_vars(entry.atom) - set(binding)), matched)
        elif entry.kind == "test":
            if _test(entry.atom, binding, window):
                walk(rest, binding, skipped, gone, matched)
            else:
                walk(rest, binding, [*skipped, entry.missing or entry.say or entry.atom[0]], gone, matched)
        elif any(gone & _vars(i.atom) for i in entry.items):
            walk(rest, binding, skipped, gone, matched)
        else:
            witness = next(_solve(entry.items, binding, index, window), None)
            if witness is None:
                walk(rest, binding, skipped, gone, matched)
            else:
                refs = [f.source.ref for _, f in witness[1] if f is not None and f.source]
                walk(rest, binding, [*skipped, f"blocked by {', '.join(refs)}"], gone, matched)

    for account in accounts:
        walk(rule.when, {"$a": account}, [], set(), 0)
    return found
