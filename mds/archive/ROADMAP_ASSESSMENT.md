# Roadmap Technical Assessment

**Assessed By:** Cascade (Claude Sonnet 4.5)
**Date:** 2025-10-16
**Source:** NEXT_PHASE_ROADMAP.md

---

## High-Level Assessment

### Overall Quality
Roadmap is well-structured with clear phase separation and realistic timelines. Priorities align with technical debt reduction before feature expansion. Sequencing follows sound engineering principles: stability → observability → features → scale.

### Key Strengths
- Defers async migration appropriately (Phase 5, conditional)
- Prioritizes code quality and maintainability early (Phase 2)
- Incremental approach prevents over-engineering
- Clear success criteria per phase

### Critical Gaps
1. **No rollback strategy** for modularization (Phase 2)
2. **Missing performance benchmarks** before/after refactors
3. **No user acceptance criteria** for dashboard (Phase 4)
4. **Undefined scale thresholds** triggering Phase 5 async migration
5. **CI definition lacks specifics** (coverage thresholds, failure policies)

### Risk Assessment
- **High Risk:** create_pdf.py modularization (10K lines, high coupling)
- **Medium Risk:** Web dashboard scope creep potential
- **Low Risk:** Type hints, error handling, logging enhancements

---

## Phase-by-Phase Analysis

### Phase 2: System Integrity & Code Quality (0-2 weeks)

**Complexity:** HIGH

**Task 1: Code Splitting create_pdf.py**
- **Blocker:** 10,184 lines with deep interdependencies
- **Risk:** Breaking existing CLI commands, symlink logic, profile management
- **Approach:**
  - Start with pure functions (image processing, file naming)
  - Extract PDF generation to `pdf/` module
  - Move deck parsing to `deck/` module
  - Keep CLI wrapper thin in create_pdf.py
- **Estimated Effort:** 16-24 hours
- **Validation:** All existing tests must pass, no behavior changes

**Task 2: Type Hint Expansion**
- **Blocker:** Legacy code without clear contracts
- **Risk:** Revealing hidden bugs during strict type checking
- **Approach:**
  - Run `mypy --strict` on new modules first (net/, db/, tools/)
  - Gradually add `# type: ignore` with tickets for legacy code
  - Focus on public APIs, defer internal implementation details
- **Estimated Effort:** 8-12 hours
- **Validation:** mypy passes on target modules

**Task 3: Error Handling Refactor**
- **Blocker:** 100+ raw exception sites across codebase
- **Risk:** Changing exception types breaks existing error handling
- **Approach:**
  - Create ProxyError hierarchy (NetworkError, DatabaseError, ValidationError)
  - Add compatibility layer: ProxyError subclasses existing exceptions
  - Migrate incrementally with deprecation warnings
- **Estimated Effort:** 6-8 hours
- **Validation:** All error paths tested, no silent failures

**Task 4: Minimal CI**
- **Blocker:** GitHub Actions setup, secrets management
- **Risk:** Flaky tests blocking PRs
- **Approach:**
  - Start with syntax check + pytest on existing tests
  - Add ruff linting (non-blocking initially)
  - Add mypy on typed modules only
  - Cache dependencies (uv, pip)
- **Estimated Effort:** 4-6 hours
- **Validation:** CI runs on PR, main branch protected

**Phase 2 Total:** 34-50 hours (1-2 weeks realistic)

**Missing Safeguards:**
- No rollback plan if modularization breaks production
- No performance regression tests
- No backward compatibility test suite

---

### Phase 3: Observability & Developer Experience (2-4 weeks)

**Complexity:** MEDIUM

**Task 1: Structured Logging Polish**
- **Blocker:** Retrofitting context IDs into existing code
- **Risk:** Performance impact from excessive logging
- **Approach:**
  - Add context manager: `with LogContext(deck_id=...)`
  - Thread-local storage for context propagation
  - Sampling for high-frequency operations
- **Estimated Effort:** 8-10 hours
- **Validation:** Context IDs appear in all major operations

**Task 2: Test Observability**
- **Blocker:** None (pytest built-in)
- **Risk:** Minimal
- **Approach:**
  - Add pytest.ini with `--durations=10 --cov=. --cov-report=html`
  - Generate coverage badge in CI
  - Add to README.md
- **Estimated Effort:** 2-3 hours
- **Validation:** Coverage report generated, badge displays

**Task 3: Documentation Automation**
- **Blocker:** CLI uses Click, not Typer (roadmap assumes Typer)
- **Risk:** Generated docs out of sync with code
- **Approach:**
  - Use `click.Context.get_help()` to extract CLI docs
  - Use `sqlite3` PRAGMA to extract schema
  - Generate markdown via script, commit to repo
  - Add pre-commit hook to regenerate
- **Estimated Effort:** 6-8 hours
- **Validation:** Docs match actual CLI/schema

**Phase 3 Total:** 16-21 hours (1 week realistic, not 2-4 weeks)

**Recommendation:** Phase 3 is under-scoped. Add:
- Performance profiling setup (py-spy, memory_profiler)
- Error rate monitoring (count exceptions by type)
- Query performance tracking (slow query log)

---

### Phase 4: UX and Feature Maturity (1-2 months)

**Complexity:** HIGH

**Task 1: Profile Config Optionalization**
- **Blocker:** Backward compatibility with directory-based profiles
- **Risk:** Config file vs directory conflicts
- **Approach:**
  - Detect config.yaml presence, use if exists
  - Fall back to directory-based if not
  - Validate config schema with pydantic
  - Migrate tool: `make profile-to-config PROFILE=name`
- **Estimated Effort:** 10-12 hours
- **Validation:** Both modes work, no breaking changes

**Task 2: Collection Tracking**
- **Blocker:** Schema change requires migration
- **Risk:** Large CSV imports (10K+ cards) performance
- **Approach:**
  - Add Alembic migration for owned_cards table
  - Batch insert with progress bar
  - Add indexes on scryfall_id, last_updated
  - CLI: `make import-collection FILE=collection.csv`
- **Estimated Effort:** 12-16 hours
- **Validation:** Import 10K cards in <30 seconds

**Task 3: Web Dashboard Polish**
- **Blocker:** Scope undefined ("polish" is vague)
- **Risk:** Feature creep, security vulnerabilities
- **Approach:**
  - Define MVP: view decks, view tokens, view collection
  - Read-only API (no mutations)
  - FastAPI + SQLite (no ORM initially)
  - Authentication: optional, local-only by default
  - Deployment: `make dashboard` runs locally
- **Estimated Effort:** 24-32 hours (highly variable)
- **Validation:** Dashboard displays data, no write operations

**Phase 4 Total:** 46-60 hours (1-2 months realistic)

**Critical Missing:**
- **No security review** for web dashboard
- **No API rate limiting** (even read-only)
- **No user acceptance criteria** (what constitutes "polished"?)
- **No mobile responsiveness requirements**

---

### Phase 5: Scalability & Future-Proofing (3-6 months)

**Complexity:** VERY HIGH

**Task 1: Async Migration**
- **Blocker:** Entire codebase uses sync I/O
- **Risk:** Massive refactor, subtle concurrency bugs
- **Approach:**
  - **DO NOT START** unless scale issues proven
  - If needed: async-only in new net/async.py module
  - Keep sync API, add async alternative
  - Gradual migration, never force async
- **Estimated Effort:** 40-80 hours (if needed)
- **Validation:** Throughput 2x+ improvement measured

**Task 2: Cache Hierarchy Formalization**
- **Blocker:** No current cache implementation to formalize
- **Risk:** Over-engineering for single-user use case
- **Approach:**
  - Document existing behavior (filesystem = L2)
  - Add LRU cache for query results (L1)
  - Track hit/miss rates in structured logs
  - Add `make cache-stats` command
- **Estimated Effort:** 12-16 hours
- **Validation:** Cache stats show >50% hit rate

**Task 3: Plugin Lifecycle**
- **Blocker:** 10 existing plugins, backward compatibility
- **Risk:** Breaking existing plugins
- **Approach:**
  - Add optional lifecycle methods (don't require)
  - Feature flag: `ENABLE_PLUGIN_LIFECYCLE=1`
  - Document in DEVELOPER_GUIDE.md
  - Migrate 1-2 plugins as examples
- **Estimated Effort:** 8-10 hours
- **Validation:** Existing plugins work unchanged

**Task 4: Metrics Light Mode**
- **Blocker:** None
- **Risk:** Minimal
- **Approach:**
  - Add timing decorators to major functions
  - Output run_summary.json on completion
  - Include: operation, duration, memory_peak, status
- **Estimated Effort:** 6-8 hours
- **Validation:** Summary generated, parseable

**Phase 5 Total:** 66-114 hours (3-6 months realistic if async included)

**Recommendation:** Phase 5 should be **fully optional**. Only execute if:
- Concurrent users >5
- Request volume >1000/day
- Current performance inadequate

---

## Automation/AI Opportunities

### High-Value Automation

**1. Code Splitting (Phase 2)**
- **Tool:** AST-based refactoring with rope/bowler
- **Agent Task:** Extract pure functions automatically
- **Validation:** Automated test suite + diff review
- **Effort Savings:** 40-50% (8-12 hours saved)

**2. Type Hint Generation (Phase 2)**
- **Tool:** MonkeyType or Pyre infer
- **Agent Task:** Run inference on test suite, generate stubs
- **Validation:** Manual review + mypy check
- **Effort Savings:** 60-70% (5-8 hours saved)

**3. Error Handling Migration (Phase 2)**
- **Tool:** AST rewriting with libcst
- **Agent Task:** Find all `raise Exception`, replace with ProxyError subclass
- **Validation:** Test suite + manual review
- **Effort Savings:** 50-60% (3-5 hours saved)

**4. Documentation Generation (Phase 3)**
- **Tool:** Custom script + Jinja2 templates
- **Agent Task:** Extract CLI help, schema, generate markdown
- **Validation:** Diff check, manual review
- **Effort Savings:** 80-90% (5-7 hours saved)

**5. Test Generation (Ongoing)**
- **Tool:** Hypothesis for property tests
- **Agent Task:** Generate test cases for parsers, validators
- **Validation:** Coverage increase, no false positives
- **Effort Savings:** 30-40% (ongoing)

### AI-Assisted Refactors

**Priority 1: create_pdf.py Modularization**
- **Approach:** AI identifies function clusters by dependency analysis
- **Output:** Proposed module structure with import graph
- **Human Review:** Validate module boundaries, approve split

**Priority 2: Exception Hierarchy Design**
- **Approach:** AI analyzes all exception sites, proposes taxonomy
- **Output:** ProxyError class hierarchy with use cases
- **Human Review:** Validate error categories, approve design

**Priority 3: Performance Regression Tests**
- **Approach:** AI generates benchmark suite from existing operations
- **Output:** pytest-benchmark tests for critical paths
- **Human Review:** Validate benchmarks meaningful, approve thresholds

---

## Recommended Adjustments

### Sequencing Changes

**MOVE UP:** Test observability (Phase 3 → Phase 2)
- **Reason:** Need coverage metrics BEFORE refactoring
- **Impact:** Prevents regression during code split

**MOVE DOWN:** Web dashboard (Phase 4 → Phase 5)
- **Reason:** High effort, low immediate value
- **Impact:** Focus on core stability first

**ADD TO PHASE 2:** Performance baseline
- **Task:** Benchmark current operations before refactoring
- **Effort:** 2-3 hours
- **Impact:** Measure regression/improvement objectively

**ADD TO PHASE 3:** Error rate monitoring
- **Task:** Track exception counts by type in logs
- **Effort:** 3-4 hours
- **Impact:** Early warning system for production issues

### Scope Adjustments

**Phase 2: Reduce Scope**
- **Remove:** Full mypy --strict (too aggressive)
- **Replace:** mypy on new code only, gradual for legacy
- **Reason:** Strict mode will block progress on 10K line file

**Phase 4: Define MVP**
- **Add:** Explicit feature list for dashboard
- **Add:** Security requirements (auth, rate limiting)
- **Add:** Performance requirements (page load <2s)
- **Reason:** "Polish" is too vague, needs acceptance criteria

**Phase 5: Add Trigger Conditions**
- **Add:** Metrics that trigger async migration
- **Add:** Scale thresholds (users, requests, data size)
- **Add:** Cost/benefit analysis requirement
- **Reason:** Prevent premature optimization

### Missing Phases

**PHASE 1.5: Rollback Safety (1 week)**
- **Task:** Create rollback plan for Phase 2 changes
- **Task:** Tag stable release before modularization
- **Task:** Document rollback procedure
- **Reason:** High-risk refactor needs escape hatch

**PHASE 2.5: Performance Validation (3 days)**
- **Task:** Run benchmarks after Phase 2 changes
- **Task:** Compare to baseline, investigate regressions
- **Task:** Document performance characteristics
- **Reason:** Validate refactor didn't degrade performance

---

## Proposed Agent Implementation Strategy

### Execution Approach

**Phase 2: Code Quality (Lead Agent: Cascade)**

**Week 1: Preparation**
1. Run test suite, establish baseline (all tests passing)
2. Generate performance benchmarks for critical operations
3. Create feature branch: `refactor/phase-2-code-quality`
4. Tag current main: `v1.0-pre-refactor`

**Week 1-2: Code Splitting**
1. Use AST analysis to identify function clusters in create_pdf.py
2. Extract pure functions first (no side effects)
3. Create modules: `pdf/layout.py`, `pdf/render.py`, `pdf/assets.py`, `deck/parser.py`
4. Move functions, update imports
5. Run test suite after each module extraction
6. Commit incrementally (1 module per commit)

**Week 2: Type Hints**
1. Run MonkeyType on test suite to generate stubs
2. Apply type hints to net/, db/, tools/ modules
3. Run mypy, fix errors
4. Add type: ignore with tickets for deferred work
5. Commit per module

**Week 2: Error Handling**
1. Define ProxyError hierarchy (NetworkError, DatabaseError, ValidationError)
2. Use libcst to find all exception sites
3. Replace incrementally, test after each batch
4. Add compatibility shims for backward compatibility
5. Commit per error type

**Week 2: CI Setup**
1. Create .github/workflows/test.yml
2. Add pytest, ruff, mypy steps
3. Configure branch protection on main
4. Test on PR, merge when green

**Validation:**
- All tests pass
- No performance regression (within 5% of baseline)
- mypy passes on typed modules
- CI runs successfully

---

**Phase 3: Observability (Lead Agent: Cascade)**

**Week 3: Logging Enhancement**
1. Add LogContext context manager to logging_config.py
2. Retrofit into major operations (fetch, build, generate)
3. Add make tail-logs utility
4. Test context propagation

**Week 3: Test Observability**
1. Add pytest.ini with coverage, durations
2. Generate coverage report in CI
3. Add badge to README.md
4. Set coverage threshold (70% initial)

**Week 3: Documentation Automation**
1. Create tools/generate_docs.py
2. Extract CLI help from Click commands
3. Extract schema from SQLite
4. Generate markdown, commit to docs/
5. Add pre-commit hook

**Week 4: Performance Monitoring**
1. Add timing decorators to critical paths
2. Log slow operations (>1s)
3. Add make performance-report command
4. Document baseline performance

**Validation:**
- Context IDs in all logs
- Coverage report generated
- Docs auto-generated and accurate
- Performance monitoring active

---

**Phase 4: Features (Lead Agent: Cascade + Human)**

**Month 2: Config System**
1. Define config schema with pydantic
2. Add config.yaml loader
3. Implement fallback to directory mode
4. Add migration tool
5. Test both modes

**Month 2: Collection Tracking**
1. Create Alembic migration for owned_cards
2. Implement CSV parser
3. Add batch insert with progress
4. Add CLI commands
5. Test with 10K card import

**Month 2-3: Dashboard (Human-led)**
1. Define MVP feature list (review with human)
2. Implement FastAPI backend (read-only)
3. Create simple UI (HTML + htmx or React)
4. Add authentication (optional)
5. Test locally
6. Document deployment

**Validation:**
- Config system works, backward compatible
- Collection import fast (<30s for 10K)
- Dashboard displays data correctly
- Security review passed

---

**Phase 5: Scale (Conditional, Human-approved)**

**Only execute if:**
- Concurrent users >5 OR
- Request volume >1000/day OR
- Current performance inadequate

**If triggered:**
1. Benchmark current performance
2. Identify bottlenecks (profiling)
3. Implement targeted optimizations
4. Consider async only if I/O-bound proven
5. Measure improvement
6. Document scale characteristics

---

### Agent Workflow Principles

**1. Incremental Commits**
- One logical change per commit
- All tests pass after each commit
- Commit messages follow conventional commits

**2. Test-First Validation**
- Run tests before starting
- Run tests after each change
- Add tests for new code
- Never commit broken tests

**3. Performance Awareness**
- Benchmark before refactoring
- Measure after changes
- Document any regressions
- Investigate >5% changes

**4. Human Checkpoints**
- Phase boundaries require approval
- High-risk changes require review
- Scope changes require discussion
- Performance regressions require explanation

**5. Rollback Readiness**
- Tag before major changes
- Document rollback procedure
- Test rollback process
- Keep escape hatch available

---

## Summary Recommendations

### Execute Immediately
1. **Add Phase 1.5:** Rollback safety (1 week)
2. **Move test observability to Phase 2:** Need coverage before refactoring
3. **Add performance baseline to Phase 2:** Measure before changing
4. **Reduce mypy scope in Phase 2:** New code only, not strict mode

### Defer/Modify
1. **Phase 4 dashboard:** Define MVP explicitly or defer to Phase 5
2. **Phase 5 async:** Make fully conditional with clear triggers
3. **Phase 5 cache:** Simplify to query result cache only

### Add Missing
1. **Security review** for web dashboard (Phase 4)
2. **Performance regression tests** (Phase 2)
3. **Error rate monitoring** (Phase 3)
4. **Scale trigger conditions** (Phase 5)

### Optimal Sequencing
1. Phase 1.5: Rollback Safety (new)
2. Phase 2: Code Quality + Performance Baseline (modified)
3. Phase 2.5: Performance Validation (new)
4. Phase 3: Observability + Error Monitoring (modified)
5. Phase 4: Config + Collection (dashboard deferred)
6. Phase 5: Scale (conditional, dashboard moved here)

### Automation Priority
1. Type hint generation (60-70% time savings)
2. Documentation generation (80-90% time savings)
3. Code splitting assistance (40-50% time savings)
4. Error handling migration (50-60% time savings)

---

**Assessment Complete**
**Recommended Action:** Approve roadmap with modifications outlined above
**Estimated Total Effort:** 116-185 hours (3-5 months realistic)
**Risk Level:** Medium (high-risk Phase 2 mitigated by rollback plan)
