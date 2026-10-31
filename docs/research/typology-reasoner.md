# Which reasoner fits an in-process Typology check?

Research for [#12](https://github.com/Samarthra/fraud_det/issues/12), under map [#11](https://github.com/Samarthra/fraud_det/issues/11). Checked on 31 October 2026.

## Recommendation

**Write a small forward-chaining evaluator and keep the Typology rules in YAML beside `rules.yaml`. Add clingo to the dev dependency group only, as a test oracle.**

The hard requirement is a proof that names facts and rules, plus a report of missing facts. Those two outputs decide this. Every candidate proves the conclusions correctly and fast enough, so the engine is not the hard part:

- **The hand-written evaluator** gets both outputs as direct by-products of how it runs. A proof is the record of which rule fired on which facts, and a missing fact is the part of a rule that found no match. The prototype did this in 203 lines, with no new runtime dependency.
- **clingo** is the best engine here, but it returns no proof. The tool that adds one, xclingo, fails on its own README example. Proofs and missing facts would be our code anyway, written around a solver, in a language the team doesn't know.
- **Soufflé** has the best built-in proof, but it isn't in-process, has no `uv` route, and its latest release prints wrong comparisons in proofs.
- **pyDatalog** installs cleanly and works, but it has no proof feature.

The cost is that we own the semantics of negation and joins. In this prototype, comparing against clingo found two real rule-loading faults on its first runs. After they were fixed, 10,000 random packs of 50 facts gave no disagreements. That's why clingo stays as a test oracle. See [Risks of this choice](#risks-of-this-choice).

## How this was tested

Unless a claim links a source, it comes from something I ran. The prototypes lived in a scratch directory outside the repo, on Python 3.13.16 under `uv` 0.13.1, on x86_64 Linux (Ryzen 5 5600H). Soufflé ran in an `ubuntu:24.04` Docker container, not on the host.

The test pack had 50 synthetic facts for one Case, and the rules were deliberately varied:

- `account_takeover`: SIM swap, password reset, new device and transfer in order, inside 2 hours.
- `verified_device_change`: a quoted text fact, plus no failed login in the previous 24 hours. This tests negation with a time window.
- `staged_claim_ring`: two claims within 30 days from accounts connected through shared devices. This tests recursion.

The clingo and hand-written versions ran all three rules. The pyDatalog and Soufflé versions ran the first two, so their timings are not strictly like for like.

## Comparison

| | clingo (ASP) | Soufflé | pyDatalog | Hand-written + YAML |
|---|---|---|---|---|
| **Proof naming facts and rules** | None built in. Workaround: carry record IDs in rule heads | Built in and best of the four, but 2.5 prints wrong comparisons | None | Direct: rule ID, premises and absence checks |
| **Negation** | Yes | Yes, stratified | Yes, stratified | Yes, stratified, checked at load |
| **Time-window arithmetic** | Yes, 32-bit integers | Yes | Yes | Yes, Python integers |
| **Missing facts** | Abduction program, 15 to 244 ms | Interactive only | Must be built on top | Direct, 0.4 ms |
| **Install with `uv` on 3.13** | Works, `cp313` wheels, 6.7 MB | No route. 257 MB of system packages | Works, `cp313` wheels | Nothing new, `pyyaml` is already a dependency |
| **Runs in-process** | Yes | No, subprocess or custom SWIG build | Yes | Yes |
| **Licence** | MIT | UPL-1.0 | LGPL-2.1 | Ours |
| **Maintenance** | Active, 5.8.2 in August 2026, version 6 in development | Master active, last release March 2025 | Restarted June 2026 after years idle | Ours |
| **Speed, about 50 facts** | 1.0 ms | 9.9 ms per process, 12.5 ms with one explain | 4.7 ms | 0.6 ms |
| **Rule readability** | Compact, unfamiliar | Compact, unfamiliar | Python operators | Longer, matches `rules.yaml` |

Speed doesn't separate them. All four are far below the time of one Sarvam call.

## clingo

**Status.** [PyPI](https://pypi.org/project/clingo/) has 5.8.2, uploaded 14 August 2026, MIT, with `cp313` manylinux wheels. The [repository](https://github.com/potassco/clingo) was pushed to on 30 October 2026. The [clingo site](https://potassco.org/clingo/) says series 6 is under development and may change until 6.0.0. The [preview API](https://potassco.org/clingo-preview/python-api/clingo/solve.html) looks different from the [5.8 API](https://docs.potassco.org/clingo/python-api/current/), so a later migration is likely.

**Install.** `uv add clingo` worked on 3.13 and brought in `cffi` and `pycparser`. The package is 6.7 MB and imports in 28 ms.

**Proof.** clingo returns the atoms that hold, not why they hold. `xclingo` is the obvious way to add a proof, and it failed here:

- The README's own example fails with a syntax error on `xclingo` 2.0b19 and 2.0b24, and on 2.0b19 with clingo 5.7.1. This is [open issue #15](https://github.com/bramucas/xclingo2/issues/15), reported on 2.0b17 in March 2025.
- [2.0b24](https://pypi.org/project/xclingo/) pins `clingo==5.8`, so plain `uv add xclingo` silently backtracks to 2.0b19 to keep clingo 5.8.2.
- It remains a beta, and [the repository's latest commits](https://github.com/bramucas/xclingo2) on its default branch date from 2022, though new betas reached PyPI in May 2026.

Other explanation tools exist, such as [ucorexplain](https://github.com/krr-up/ucorexplain) and [xASP2](https://arxiv.org/pdf/2308.15879). I did not test them. ucorexplain's README describes a restricted fragment.

The workable approach is to carry record IDs in every rule head, which gave correct citations:

```prolog
proof(account_takeover, A, (E1,E2,E3,P)) :-
    event(E1,A,"sim_swap",T1), event(E2,A,"password_reset",T2), T1 < T2,
    event(E3,A,"device_enrolled",T3), T2 < T3,
    pays(P,A,_,_,T4), T3 < T4, T4 - T1 <= 7200.
```

This is a convention, not a feature. An author who drops an ID gets a shorter proof and no error. Absence checks and intermediate rules such as `connected` don't appear in the proof without more work.

**Missing facts.** Abduction works well in principle. A choice rule assumes events and `#minimize` finds the fewest, and it correctly named the one missing event in each near miss. But assumed events need a time, so someone has to choose the candidates. Times one second after each known event took 15 ms and gave a wrong answer when the first step was missing, assuming three events instead of one. Adding one second before each known event fixed that and took 244 ms. Each rule needs a second relaxed copy.

**Two traps.**

- **Silent integer wraparound.** `a(3000000000).` in program text gives `a(-1294967296)` with no error. Epoch seconds fit until 2038, but epoch milliseconds would corrupt time windows. `clingo.Number` does raise `OverflowError`.
- **Injection through quoted text.** Building the program as a string lets a quoted text fact add rules: a crafted quote produced a forged `proof(...)`. Adding facts through the [`Backend` API](https://docs.potassco.org/clingo/python-api/5.8/clingo/backend.html) is safe, and the same quote produced nothing. Text facts come from the model reading untrusted text, so this matters.

**Determinism.** The rules gave exactly one answer set, because they use no choice rules.

## Soufflé

**Status.** [Latest release](https://github.com/souffle-lang/souffle/releases/tag/2.5) is 2.5, March 2025, and master is 43 commits ahead. UPL-1.0, with commits as recent as October 2026 and 134 open issues and pull requests. Nothing usable named Soufflé is on PyPI: the [`souffle`](https://pypi.org/project/souffle/) package there is an unrelated 2018 project.

**Install.** There is no `uv` route. [Official routes](https://souffle-lang.github.io/build) are packages or a CMake source build, and the [2.5 release](https://github.com/souffle-lang/souffle/releases/tag/2.5) ships `.deb` and `.rpm` files only. `pacman` has no `souffle` package in the repositories on this Arch machine, so it would need a source build or a container. On Ubuntu 24.04 the `.deb` added 257 MB, and it depends on `g++`, `mcpp` and several `-dev` packages. On that machine `-s python` also failed because `swig` wasn't installed, and the [SWIG docs](https://souffle-lang.github.io/swig) require a build with `SOUFFLE_SWIG_PYTHON=ON`.

**Proof.** This is its strength. [`souffle -t explain`](https://souffle-lang.github.io/provenance) gives a proof tree with rule numbers and, after `format json`, machine-readable output. Piping commands to stdin worked, and absence checks appear as axioms such as `!failed_before("ACC-10042", 1792001800)`. `explainnegation` shows why a tuple doesn't hold, but it's an interactive session, and the [docs](https://souffle-lang.github.io/provenance) state that explaining non-existence can't be done automatically. So it doesn't give us missing facts.

**A defect that matters.** The 2.5 proof for `account_takeover` contained `25 < 25` and `26 <= 26` in place of real comparisons, so a proof shown to an Analyst would have included nonsense. This is [issue #2466](https://github.com/souffle-lang/souffle/issues/2466), fixed by [PR #2585](https://github.com/souffle-lang/souffle/pull/2585) in July 2026, after the last release. Taking the fix means building from master.

**Compile mode.** Compiling to a binary took 11.7 s, and the binary then ran in 2 ms. Rules would be fixed at build time unless we keep `g++` on the machine.

## pyDatalog

**Status.** It is maintained again. The [README](https://github.com/pcarbonn/pyDatalog) says support restarted in June 2026, and the [changelog](https://github.com/pcarbonn/pyDatalog/blob/master/CHANGELOG.md) jumps from 2016 to 0.20.8 in June 2026. [PyPI](https://pypi.org/project/pyDatalog/) has 0.22.4 with `cp313` wheels, and a pure Python wheel. The licence is LGPL-2.1. All of this rests on one maintainer in one burst of work, with no commits since 13 June 2026.

**Install.** `uv add pyDatalog` worked on 3.13. Import printed a `SyntaxWarning` for an invalid escape sequence in `pyParser.py`.

**Behaviour.** Negation and time arithmetic gave the right answers, including when a failed login was removed. Four threads each loading their own facts gave no errors and no wrong answers in 80 runs, which is a small test, not proof of thread safety.

**Proof.** There is none. Searching the installed package for `explain`, `provenance` and `proof` found nothing, and the [docs](https://pydatalog.readthedocs.io/en/latest/) mention none. Carrying IDs in heads would work as it does in clingo, with the same weaknesses and a less proven engine.

## Hand-written evaluator with YAML rules

The prototype was 203 lines of Python on top of `pyyaml`. It evaluates rules in stratified layers to a fixed point, so derived facts and recursion work. It refuses negation through a cycle at load.

```yaml
- id: verified_device_change
  title: Customer confirmed the new device and no login failed in the day before
  typology: true
  head: [verified_device_change, $a]
  when:
    - event: [$device, $a, device_enrolled, $t]
    - text: [$quote, $device, customer_confirmed_device, $words]
    - absent:
        - login: [$l, $a, failed, $d, $tl]
        - at_most_before: [$tl, $t, 86400]
```

**Proof.** Each derived fact stores the rule, the premises and the absence checks that held. The output needed no post-processing, and nested derived facts expanded down to source records:

```text
('staged_claim_ring', 'CLM-1', 'CLM-2')  [rule staged_claim_ring]
  ('claim', 'CLM-1', 'ACC-10042', 1792086400)  [source record]
  ('claim', 'CLM-2', 'ACC-3', 1792432000)  [source record]
  ('connected', 'ACC-10042', 'ACC-3')  [rule connected_step]
    ('connected', 'ACC-10042', 'ACC-2')  [rule connected_base]
    ...
```

Because the evaluator holds full source facts, each leaf maps directly to a `source_ref`. Rule `title` gives the Analyst a sentence for each step.

**Missing facts.** The same walk lets a rule skip a body atom and counts what it skipped, keeping the partial match with the fewest gaps. It works without choosing candidate times, and it covers gaps anywhere in the sequence:

| Near miss | Reported |
|---|---|
| No new device | Has `EVT-1`, `EVT-2`, `TXN-1`. Missing a `device_enrolled` event on `ACC-10042` |
| No SIM swap | Has `EVT-2`, `EVT-3`, `TXN-1`. Missing a `sim_swap` event |
| Failed login inside the 24 hours | `blocked_by` `LOG-1` |
| Transfer 3 hours after the swap | Tied answers, of which two were shown: no transfer that fits, or no SIM swap that fits |

The last row is weaker than it should be. An Analyst would want "the transfer came 1 hour too late". The prototype discards a fact when a time test fails, so the build should keep the failed test as the reason.

**Speed.** 0.64 ms for all rules and 0.37 ms for missing facts on 50 facts. On 200 facts it took 6.2 ms and 13.3 ms, against 2.3 ms for clingo. That's slower growth to watch, but nowhere near mattering at this size.

**Injection.** Quoted text stays a Python string and is never parsed as rules, so the clingo trap doesn't exist here.

## Rule readability

The ASP and Datalog forms are shorter, and they read well to someone who knows logic programming. The YAML is longer but has a list of conditions to read top to bottom, an `id`, and a `title`, and a future developer has already edited `rules.yaml`. It also fits [the map's open question](https://github.com/Samarthra/fraud_det/issues/11) on where rules live: they can sit beside `rules.yaml` and be edited in the same way.

## Risks of this choice

- **We own correctness.** I checked this with a differential test against clingo: same conclusions, and same record IDs for `account_takeover` and `verified_device_change`, on 10,000 random packs of 50 facts, half of them bunched into 5 hours so that the 2-hour rule fired. There were no disagreements across 53,374 proofs. Only conclusions were compared for `staged_claim_ring`, and the test doesn't cover missing-fact output.
- **Silent rule failures.** Each of these took a run of the differential test to find, because a rule that can't match simply proves nothing:
  - `[?a, ?b]` in a YAML flow list parses as keys, not strings. The prototype now uses `$a`.
  - A key called `no` parses as the boolean `False` under [YAML 1.1](https://yaml.org/type/bool.html), which PyYAML loaded here. The prototype now uses `absent`.

  The build must therefore validate rules strictly at load: known keys only, and every variable bound. It should also have a test that each Typology fires on a sample.
- **Scope creep.** If rules ever need disjunction, optimisation or thousands of facts, this evaluator is the wrong tool. Move to clingo then. The rule-to-proof contract stays the same, so only the evaluator changes.
- **The oracle has a cost.** It needs the rules written twice, or a small YAML-to-ASP generator for tests. One differential test in the dev group is enough, and it should be dropped if it becomes a burden.

## Not verified

- **Only three test rules were written.** The five named Typologies were not, so a rule shape that this evaluator can't express may yet appear.
- **Nothing ran inside FastAPI or LangGraph.** Each timing is one engine in a loop, on a single process.
- **Soufflé was not run on the host OS**, and master, which has the fix for #2466, was not built. Its timings come from a container.
- **`explainnegation`** was not scripted. I relied on its docs.
- **ucorexplain and xASP2** were read about, not run.
- **The 257 MB figure** is measured on a clean container, so it includes dependencies that a dev machine may already have.
- **The `Backend` claim** was confirmed by running it. I confirmed the docs URL loads, but did not read that page's text.

## Sources

- clingo: [site](https://potassco.org/clingo/), [repository](https://github.com/potassco/clingo), [PyPI](https://pypi.org/project/clingo/), [Python API 5.8](https://docs.potassco.org/clingo/python-api/current/), [guide](https://potassco.org/guide/)
- xclingo: [repository](https://github.com/bramucas/xclingo2), [PyPI](https://pypi.org/project/xclingo/), [issue #15](https://github.com/bramucas/xclingo2/issues/15)
- Soufflé: [repository](https://github.com/souffle-lang/souffle), [provenance](https://souffle-lang.github.io/provenance), [rules](https://souffle-lang.github.io/rules), [build](https://souffle-lang.github.io/build), [SWIG](https://souffle-lang.github.io/swig), [embedding](https://souffle-lang.github.io/interface), [provenance paper](https://arxiv.org/pdf/1907.05045)
- pyDatalog: [repository](https://github.com/pcarbonn/pyDatalog), [docs](https://pydatalog.readthedocs.io/en/latest/), [PyPI](https://pypi.org/project/pyDatalog/)
- YAML: [boolean type for YAML 1.1](https://yaml.org/type/bool.html), [PyYAML docs](https://pyyaml.org/wiki/PyYAMLDocumentation)
