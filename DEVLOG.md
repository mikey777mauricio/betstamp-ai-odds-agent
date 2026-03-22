# Development Log — Betstamp AI Odds Agent

> This log captures my development process chronologically, including architecture decisions, prompt iterations, what I delegated to AI vs. wrote myself, and what I learned along the way.

---

## Phase 0: Reading the Spec & Initial Architecture (45 min)

Before writing a line of code, I spent time decomposing the problem. The spec describes a manual workflow that takes 30-45 minutes every morning. The key insight: this isn't a chatbot problem — it's a **data pipeline with an LLM synthesis layer**.

**My initial architecture sketch:**

```
Sample Data → Data Store → Detection Tools → Analysis Tools → Agent (LLM) → Briefing
                                                                    ↓
                                                              Chat Interface
```

**First principle I committed to:** The LLM orchestrates; Python computes. Every number in the briefing must come from a deterministic, tested function — not from the model's token generation. This is non-negotiable for anything touching real money. I've built production ML systems where a single floating-point hallucination in a pricing model caused a six-figure error. The LLM is good at synthesis and prose; it is terrible at arithmetic. Separate the concerns.

**Stack selection rationale:**
- **Strands SDK + Claude Sonnet 4**: Best tool-use capabilities in the industry. Strands gives me `@tool` decorators, automatic schema generation from Python type hints, and multi-turn conversation management. I chose it over LangChain because it's lighter, has fewer abstraction layers, and the `@tool` pattern maps directly to "write a function, decorate it, done." I chose it over raw API calls because I don't want to hand-roll tool dispatch loops and message history.
- **FastAPI**: Async, auto-generated OpenAPI docs, native Pydantic integration. Standard for Python AI services.
- **Next.js + TypeScript**: Type-safe frontend with SSR capability. The spec says UI is only 15% — I wanted something I could move fast with.
- **In-memory data store**: 80 records. No database needed. But I designed the `OddsStore` with a clean interface so it's swappable to Postgres later.

---

## Phase 1: Math Foundation & Test-First Development (2 hrs)

I started with the math because everything else depends on it. The spec provides exact formulas — implied probability, vig, no-vig fair odds. I implemented each as a pure function in `math_utils.py` and wrote tests against the spec's examples before moving on.

**28 tests in `test_math.py`** covering:
- American → implied probability (both positive and negative odds)
- Vig calculation with the spec's exact example: -110/-110 → 4.76%
- No-vig fair odds normalization
- Edge cases: zero odds, boundary probabilities, round-trip conversions

```python
# Example: verifying against the spec's exact numbers
def test_vig_standard_juice():
    # -110 / -110 → 52.38% + 52.38% = 104.76% → 4.76% vig
    vig = calculate_vig(-110, -110)
    assert vig == pytest.approx(0.0476, abs=0.001)
```

**Why test-first:** If the math is wrong, every downstream component (detection, analysis, briefing) produces garbage. 28 tests running in 0.03s gave me a safety net for the rest of the build. I could refactor freely knowing the foundation was solid.

---

## Phase 2: Detection Layer — Finding the Seeded Anomalies (2 hrs)

The spec says there are 2-3 stale lines, 1-2 outlier prices, and at least 1 arbitrage opportunity. I examined the sample data to identify the ground truth, then wrote detection algorithms to find them.

### Stale Line Detection

Straightforward: for each game, find the most recent `last_updated` across all books. Flag any book more than 2 hours behind. The threshold is configurable via environment variable.

**Ground truth found:**
| Anomaly | Sportsbook | Game | Hours Behind |
|---------|-----------|------|-------------|
| Stale | Caesars | ATL @ CHA | 10.6 hrs |
| Stale | PointsBet | LAL @ BOS | 9.3 hrs |
| Stale | BetRivers | DAL @ PHX | 7.1 hrs |

### Outlier Detection — The MAD Decision

**What AI got wrong:** Claude initially suggested standard deviation for outlier detection. I implemented it, tested it, and it **missed the BetMGM moneyline outlier** (-195 vs consensus ~-130). The z-score came out to 1.6 — below my 2.0 threshold. Classic masking effect: the outlier inflated the standard deviation, hiding itself.

**My fix:** Switched to Median Absolute Deviation (MAD). MAD uses the median instead of the mean, so a single extreme value can't distort the measure. The same BetMGM outlier jumped to a z-score well above 2.0 — detected immediately.

I also added minimum sensitivity floors (MAD=0.5 for spread/total lines, MAD=0.01 for implied probabilities) to prevent division-by-zero when all books agree perfectly.

**Outliers found:**
| Anomaly | Sportsbook | Game | Market | Detail |
|---------|-----------|------|--------|--------|
| Outlier | BetMGM | MIL @ DEN | Moneyline | -195 vs consensus ~-130 |
| Outlier | Caesars | POR @ UTA | Total | 223.5 vs consensus ~217 |

### Arbitrage Detection

For each game and market, find the best odds on each side across all books. If combined implied probability < 100%, it's an arb. The math uses `check_arbitrage()` from math_utils, which computes exact profit percentages and optimal stake allocation.

**24 tests in `test_detection.py`** — critically, these test against the specific seeded anomalies, not just "something was returned." Plus false-positive checks (CLE/OKC game returns 0 stale lines).

---

## Phase 3: Analysis Layer — Making the Data Actionable (1.5 hrs)

Detection finds problems. Analysis surfaces opportunities. I built five analysis functions:

1. **`analyze_market_vig`** — Per-book vig on every market. Identifies the sharpest book.
2. **`find_best_lines`** — Best available odds on each side across all books. Calculates fair odds via median normalization and edge percentages.
3. **`rank_sportsbooks`** — Composite score (50% vig quality + 50% data reliability). Grades A+ through F.
4. **`find_value_opportunities`** — Scans all games for positive-edge bets where offered odds beat fair probability.
5. **`get_market_summary`** — Consensus spread, total, win probability, and ranges per game.

**16 tests in `test_analysis.py`** — verifies Pinnacle ranks high (lowest vig), best line detection is actually the best (cross-verified), sort orders are correct.

---

## Phase 4: Agent Integration — The Prompt Engineering Journey (3 hrs)

This is where the hard part started. The tools all worked individually. Making the LLM use them correctly was a different challenge.

### Prompt V1: Goal-Only (Failed)

```
"You are a sports betting analyst. Analyze this odds data and generate a report."
```

**What happened:** The agent treated this as creative writing. It generated plausible-sounding analysis with realistic numbers that were completely fabricated. Zero tool calls. The output read well but was fiction.

**Lesson:** Giving an agent a goal without a process is like giving a junior developer a Jira ticket with no acceptance criteria.

### Prompt V2: Structured Output (Partially Worked)

Added explicit section structure and "ALWAYS use these tools." Better — the agent called `get_games()` consistently, sometimes `run_detection()`, but often skipped `run_analysis()` and filled in remaining sections with educated guesses.

**Lesson:** "Always use tools" doesn't tell the agent *which* tools or *when*. Structure without process is a template, not a recipe.

### Prompt V3: Process-First (Shipped)

The breakthrough was specifying a 4-step process:
1. Get the lay of the land (`get_games`, `get_market_summary`)
2. Run detection (`run_detection`)
3. Run analysis (`run_analysis`)
4. Synthesize into the briefing

Combined with per-section formatting rules, explicit math citation requirements, and confidence tier handling (HIGH → recommend action, MEDIUM → note uncertainty, LOW → monitor only).

**Key insight:** Process-first prompts outperform goal-first prompts consistently. This aligns with chain-of-thought research — the model performs better with a reasoning scaffold.

### Chat Prompt — The Re-Verify Pattern

Initially, the chat agent had the briefing text in its system prompt and would "recall" numbers rather than re-computing them. If the briefing said "9.2 hours behind," the chat would parrot it without verification.

**Fix:** "Use your tools to re-verify any claims rather than relying on the previous briefing text." More tool calls (more latency), but grounded answers. I also added explicit scope boundaries — the chat only discusses odds, betting, and the briefing data. Off-topic questions get a polite decline.

---

## Phase 5: Three Iterations to the Right Architecture (3 hrs)

This was the most important phase. I went through three distinct architectures, each teaching me something about where LLMs belong in a data pipeline.

### Iteration 1: LLM Does Everything (Failed)

My first approach was the naive one: give the agent access to the raw data and let it do the math. The prompt said "calculate the vig" and "check for arbitrage." The LLM would read the odds, do arithmetic in its response, and output a formatted briefing.

**What went wrong:**
- The LLM computed -110/-110 vig as "4.5%" (correct answer: 4.76%). Close enough to look right, wrong enough to matter.
- Arbitrage calculations were inconsistent — same two odds would produce different profit percentages across runs.
- A single briefing consumed ~8,000 tokens of output because the LLM was "showing its work" with step-by-step math.
- No way to test correctness — the math was embedded in unstructured prose.

**Lesson:** LLMs are unreliable at arithmetic. "Most of the time correct" is not acceptable when someone might bet real money on the output.

### Iteration 2: Sequential Agentic Workflow (Better, But Expensive)

I moved the math into `@tool`-decorated functions and let the agent call them in a sequential agentic loop. The LLM would call `get_games()`, then `detect_stale_lines()` for each game, then `analyze_vig()`, etc. The numbers were now correct (deterministic Python), but a new problem emerged.

**What went wrong:**
- The agent made 30-50 tool calls per briefing, each requiring an LLM round-trip to decide what to call next. Briefings took 60-120 seconds.
- Token cost was high — the LLM's "reasoning" about which tool to call next consumed thousands of tokens. The tool dispatch logic was trivial (always the same sequence), but the LLM was re-discovering it every time.
- The LLM would sometimes skip tools or call them in suboptimal order, requiring prompt engineering to enforce the sequence.
- Output formatting was still markdown — the LLM decided how to present the tool results, leading to inconsistent section ordering and broken tables.

**Lesson:** If the tool-calling sequence is deterministic and always the same, the LLM shouldn't be deciding it. You're paying for "intelligence" to make a decision that has exactly one correct answer.

### Iteration 3: Programmatic Pipeline + LLM Narrative (Shipped)

The breakthrough: **run the entire detection and analysis pipeline in pure Python** (no LLM), capture results in typed Pydantic models, and only invoke the LLM once at the end to write a short executive summary over the pre-computed data.

```
Python Pipeline (deterministic, ~2 seconds):
  get_games() → detect_stale_lines() → detect_outlier_odds() → detect_arbitrage()
  → analyze_vig() → find_best_lines() → rank_sportsbooks() → find_value_opportunities()
  → Build Pydantic StructuredBriefing

LLM Call (single invocation, ~5 seconds):
  "Here is the structured data. Write a 250-word executive summary."
```

```python
class StructuredBriefing(BaseModel):
    overview: MarketOverview
    stale_lines: list[StaleLineAlert]
    outlier_odds: list[OutlierAlert]
    arbitrage: list[ArbitrageOpportunity]
    value_plays: list[ValuePlay]
    sportsbook_rankings: list[SportsbookRanking]
    narrative: str  # LLM writes only this
    quality_metrics: QualityMetrics
```

**The numbers tell the story:**

| Metric | Iteration 2 (Agentic) | Iteration 3 (Programmatic) |
|--------|----------------------|---------------------------|
| Generation time | 60-120s | 10-20s |
| LLM round-trips | 30-50 | 1 |
| Output tokens | ~8,000 | ~500 |
| Math correctness | 100% (tools) | 100% (same tools) |
| Format consistency | Variable | Always structured |
| Testable | Partially | Fully |

**Why this is the right architecture:**
- Numbers are always correct (deterministic Python, not LLM generation)
- UI is always consistent (React components render typed data, no markdown parsing)
- Token cost drops ~90% (one LLM call vs. 30-50 round-trips)
- 6x faster (parallel Python calls vs. sequential LLM-mediated tool use)
- Fully testable — validate the Pydantic schema, not grep for strings
- Evaluable — structured data enables automated quality scoring against ground truth

The LLM still adds value — the narrative summary contextualizes the data, highlights what matters most, and gives actionable recommendations. But it does what LLMs are good at (synthesis, prioritization, prose) and nothing they're bad at (arithmetic, formatting, deterministic sequencing).

The arbitrage cards now include exact stake allocation: "Place $612.35 on Side A at BetMGM (+165) and $387.65 on Side B at FanDuel (-155). Guaranteed $81.20 profit." This is computed in Python, not generated by the LLM.

---

## Phase 6: Evaluation Pipeline — Measuring What Matters (2 hrs)

This is the part I'm most proud of. Building an agent is one thing. Building a system that *knows when it's wrong* is what separates prototypes from production.

### The Evaluation Philosophy

Most AI demos have no way to measure quality. "It looks about right" is not an acceptance criterion. I built a `BriefingEvaluator` that scores every briefing on five automated metrics, with the option to run evaluation after each generation via a toggle in the UI.

### Four Metrics, Each Testing a Different Failure Mode

**1. Completeness (20% of composite):** Does the briefing cover all required concepts — market context, anomaly discussion, arbitrage analysis, value opportunities, and sportsbook assessment?

Initially this was a simple keyword matcher (does "market overview" appear as a header?). It scored poorly because our structured pipeline produces a flowing executive summary, not a section-header document. I iterated to concept-based matching with synonym groups — "stale" or "outlier" or "flag" satisfies the anomaly concept. This is a better test anyway: it measures whether the narrative *discusses* the concept, not whether it uses a specific formatting convention.

**2. Tool Coverage (20%):** Did the agent invoke all three required tool categories (data, detection, analysis)? This catches prompt regressions where the LLM decides to skip a step.

**3. Structured Completeness (30%):** Are all eight sections of the structured output populated? (5 data sections + overview + narrative + quality metrics). Catches pipeline failures where a tool returns empty results that get silently swallowed.

**4. Consistency (30%):** The most sophisticated metric. Does the narrative agree with the structured data? Four sub-checks:
- **Count consistency:** "3 stale lines detected" → are there actually 3 in `stale_lines[]`?
- **Entity consistency:** Sportsbooks named in the narrative exist in the structured data
- **Presence consistency:** Narrative doesn't say "no arbitrage found" when `arbitrage[]` has entries
- **Number consistency:** Profit percentages and vig numbers in the narrative match structured data values

This metric catches the most dangerous failure mode in AI systems: **confident hallucination over real data**. The narrative sounds authoritative, the numbers look plausible, but they don't match what the tools actually computed.

### Why Consistency Gets 30% Weight

In a financial context, an agent that says "no anomalies found" when the data contains three stale lines is worse than an agent that reports nothing at all. The user trusts the narrative and makes decisions on it. Consistency scoring ensures the narrative is grounded in the actual structured output — not in the LLM's creative interpretation of what "should" be there.

### Evaluation in the UI

The frontend has a "Run quality evaluation" toggle next to the generate button. When enabled, evaluation runs automatically after briefing generation and displays a panel with score bars, color-coded thresholds (green ≥80%, amber ≥50%, red <50%), and a composite score badge. This makes quality visible to both the user and the reviewer.

**26 tests in `test_eval.py`** — verifies each metric against known good/bad inputs, composite weight calculations, and edge cases.

---

## Phase 7: Real-Time Feedback & Streaming (1.5 hrs)

### Briefing Generation: SSE Tool Trace

A briefing takes 15-30 seconds. Staring at a spinner is unacceptable. I added SSE (Server-Sent Events) streaming that emits structured events as the agent works:

- `tool_call` events with tool name and inputs
- `done` event with status

The frontend renders this as a live timeline with a stage progress bar, color-coded categories (Data Collection → Anomaly Detection → Market Analysis), elapsed timer, and animated tool call entries.

**Implementation detail:** The structured pipeline bypasses `@tool` wrappers (faster — no LLM overhead for deterministic calls), so I manually call `_log_tool_call()` at each stage to keep the SSE stream populated. This gives the user visibility into what's happening without sacrificing performance.

### Chat: `stream_async` Integration

The Strands SDK exposes `agent.stream_async()` — an async generator that yields events including text chunks and tool use information. I integrated this into the chat endpoint so responses stream in real-time.

**What didn't work initially:** My first attempt ran the full `agent(message)` call synchronously, then yielded events post-hoc. This was pseudo-streaming — the user waited for the full response, then saw it all at once.

---

## Phase 8: Production Hardening (Autonomous Improvement Loop)

Ran 10 cycles of automated audit → fix → test. This phase was about finding edge cases and closing gaps.

**Production Rate Limiting:**
- Added in-memory rate limiter on LLM-heavy endpoints (`/api/briefing/trigger`, `/api/chat`) — 30 requests per hour max. This protects against runaway API costs when deployed with my own Anthropic key. Uses a sliding window with `deque` + `threading.Lock` for thread safety. Non-LLM endpoints (health, data, status polling) are unaffected.

**Resilience & Correctness:**
- All 16 tool wrappers: try/except with graceful degradation (partial briefing > no briefing)
- Pydantic `field_validator`: confidence clamped 0-1, composite score clamped 0-100
- NaN/Inf guard on probability conversion (previously silent corruption)
- Arbitrage stake rounding: `stake_b = round(1000.00 - stake_a, 2)` guarantees sum = $1000.00
- Conversation history validation: malformed messages logged and skipped, not crashed on
- Race condition fix in `chat_stream`: remaining tool calls yielded in `finally` block before trace cleanup
- Data upload graceful handling: `get_games()` uses `.get()` with defaults for optional fields

**Observability:**
- `QualityMetrics` model: overall confidence, high-confidence %, data warnings
- Health endpoint: data_loaded state, games_count, model ID
- Frontend quality bar: confidence indicator, alert breakdown, generation timing
- "How It Works" expandable panel: explains the 3-stage pipeline, architecture, and evaluation system to technical reviewers

**Frontend Polish:**
- SSE retry timeout memory leak fixed (zombie EventSource connections)
- Error path cleanup: EventSource properly closed on trigger failure
- Card hover effects, entrance animations, gradient backgrounds
- Mobile responsive layout (flex-col → flex-row at lg breakpoint)
- Keyboard accessible tooltips (Escape key, `aria-expanded`, `aria-label`)
- Interactive glossary: 16 betting terms with click-to-expand definitions

**Thread Safety:**
- `_last_briefing` protected by `threading.Lock` (written from background thread, read from async handlers)
- Per-request `threading.local()` for chat traces (prevents interleaving under concurrent requests)
- Shared trace list for briefing SSE (single generation at a time, polled from different async context)
- 5-minute timeout on briefing generation (stuck LLM → error state, not infinite spinner)
- Thread safety tests: concurrent reads, concurrent read/write races

---

## How I Used AI During Development

**Claude Code (Opus 4.6)** was my primary development tool throughout.

**What I delegated to AI:**
- Project scaffolding and boilerplate (FastAPI setup, Next.js config, Docker files)
- First drafts of test cases — I described what anomalies exist in the data, AI wrote the assertions
- CSS/Tailwind styling for the frontend components
- Strands SDK tool wrapper boilerplate
- Iterating on evaluation metric implementations (the consistency sub-checks)

**What I wrote/designed myself:**
- The 3-stage pipeline architecture (Detect → Analyze → Narrate)
- All odds math formulas (verified against spec examples)
- Detection algorithms — MAD-based outlier detection, stale line thresholds, arbitrage scanner
- The sportsbook ranking scoring model
- All system prompts (3 iterations with specific failure analysis at each stage)
- The tool separation strategy (briefing: high-level pipeline vs. chat: all 16 tools)
- The structured output pivot (Phase 5) — the single biggest quality improvement
- Evaluation metric design — what to measure, why, and the weight distribution
- Thread safety model and concurrency architecture
- The consistency scorer concept (narrative vs. structured data agreement)

**What AI got wrong that I had to fix:**
1. **Standard deviation for outlier detection** — missed seeded anomalies due to masking effect. Replaced with MAD.
2. **Dumping all 80 records into LLM context** — redesigned to use `@tool` functions that query the data store.
3. **Streaming implementation** — initial version was synchronous with post-hoc event emission. Integrated `stream_async` for real streaming.
4. **`datetime.utcnow()`** — deprecated in Python 3.12. Caught by tests.
5. **Variable shadowing in stale detection** — `r` vs `record` bug. Caught by self-audit.
6. **Rigid completeness scoring** — keyword matching penalized good narratives that discussed concepts without using exact header names. Iterated to synonym-based concept matching.

---

## Architecture Decision Records

### ADR-001: "LLM Orchestrates, Python Computes"

**Context:** The spec says "your agent's math needs to be right — and you need to verify it is."

**Decision:** All odds math lives in pure Python functions. The LLM never computes a number — it calls a tool, receives JSON, and cites it.

**Rationale:** LLMs are unreliable at arithmetic. "Most of the time correct" is not acceptable when someone might act on the output. 168 deterministic pytest assertions guarantee correctness independent of the model.

**Trade-offs:** The agent can only answer questions its tool suite covers. More tools = more capability but more surface area to test.

### ADR-002: Strands SDK Over Raw API / LangChain

**Decision:** Strands SDK with Claude Sonnet 4.

**Rationale:** `@tool` decorator with automatic schema generation, minimal boilerplate, the agent decides tool call sequence from the prompt rather than hard-coded orchestration. Lighter than LangChain, more featured than raw API.

**Trade-offs:** Smaller community. Streaming support was limited (led to the `stream_async` integration in Phase 7).

### ADR-003: Structured Output Over LLM-Formatted Markdown

**Decision:** Run detection/analysis tools deterministically, capture in Pydantic models, LLM writes narrative only.

**Rationale:** Eliminates an entire class of bugs (markdown formatting, inconsistent sections, hallucinated numbers). The frontend renders typed data with dedicated components. LLM cost drops ~80%. And critically, it enables automated evaluation — you can't score consistency between narrative and data if there's no structured data.

**Trade-offs:** Less flexible — new sections require both a Pydantic model and a React component. Worth it for reliability and evaluability.

### ADR-004: MAD for Outlier Detection

**Decision:** Median Absolute Deviation instead of standard deviation.

**Rationale:** SD suffers from the masking effect — outliers inflate the measure, hiding themselves. MAD is robust because the median is resistant to extreme values. Validated: the seeded BetMGM outlier went from z=1.6 (undetected with SD) to z>2.0 (detected with MAD).

### ADR-005: Evaluation-First Design

**Decision:** Build automated evaluation into the core product, not as an afterthought.

**Rationale:** An AI agent that can't be measured can't be trusted. The evaluation pipeline catches three categories of failures:
1. **Tool failures** (tool coverage) — agent skipped a step
2. **Data failures** (structured completeness) — pipeline produced incomplete results
3. **Synthesis failures** (consistency) — LLM narrative contradicts computed data

The composite score serves as a regression test for prompt changes — if a prompt edit drops consistency from 95% to 60%, you know immediately.

---

## Test Summary

**168 tests passing in ~0.5s:**

| File | Tests | What It Covers |
|------|-------|---------------|
| `test_math.py` | 34 | Every formula against spec examples + edge cases (NaN, Inf, extremes) |
| `test_detection.py` | 29 | Specific seeded anomalies, false-positive absence, confidence scoring |
| `test_analysis.py` | 20 | Vig correctness, best line detection, rankings, value opportunities |
| `test_data_store.py` | 10 | CRUD, load/replace/reset, empty queries, optional field handling |
| `test_eval.py` | 21 | Evaluator scoring — completeness, tool coverage, structured data, consistency, composite weights |
| `test_models.py` | 14 | Pydantic model validation, confidence/score clamping, round-trip serialization |
| `test_edge_cases.py` | 23 | Math boundaries, thread safety, extreme odds, NaN guards, concurrent access |
| `test_api.py` | 17* | API integration tests (all endpoints, conditional skip without SDK) |

*\*test_api.py tests are skipped in CI without the Strands SDK installed.*

---

## Anomalies Detected (Ground Truth)

| Type | Sportsbook | Game | Detail | Confidence |
|------|-----------|------|--------|------------|
| Stale Line | Caesars | ATL @ CHA | 10.6 hrs behind freshest line | HIGH |
| Stale Line | PointsBet | LAL @ BOS | 9.3 hrs behind freshest line | HIGH |
| Stale Line | BetRivers | DAL @ PHX | 7.1 hrs behind freshest line | HIGH |
| Outlier | BetMGM | MIL @ DEN | Moneyline -195 vs consensus ~-130 | HIGH |
| Outlier | Caesars | POR @ UTA | Total 223.5 vs consensus ~217 | HIGH |

All 5 seeded anomalies are detected with HIGH confidence. Anomaly recall: 100%.

---

## What I'd Improve With More Time

1. **Live odds API integration** — Connect to The Odds API for real-time feeds. The `OddsStore` abstraction already supports `load_from_api()`.

2. **LLM-as-judge evaluation** — A second LLM scores briefing quality on subjective dimensions (clarity, actionability, prioritization). Combined with the automated metrics, this gives both objective and subjective quality signals.

3. **Historical line movement** — Track lines over time. "This spread moved 2 points in the last hour" is more actionable than a snapshot.

4. **Multi-agent orchestration** — Split into Detector, Analyst, and Writer agents. The Writer has no data tools — it literally cannot hallucinate numbers.

5. **Prompt A/B testing framework** — Run prompt variants against the same dataset, score with evaluation metrics, statistical comparison. The evaluation pipeline already provides the scoring; you just need a runner.

6. **User-configurable thresholds** — Let analysts set their own stale-line threshold, minimum edge, and z-score sensitivity.

7. **Bet tracking / P&L** — After acting on a recommendation, track the outcome. Closes the feedback loop from recommendation → decision → result → improved recommendations.

8. **Game-time urgency signals** — "Game tips off in 3 hours — this arb window may close." Time-sensitive alerts that increase urgency as tip-off approaches.
