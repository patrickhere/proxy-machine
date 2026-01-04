# Phase 1.5 & 2 Execution Kickoff

**Date:** 2025-10-16
**Lead Agent:** Cascade (Claude Sonnet 4.5)
**Approved Roadmap:** FINAL_APPROVED_ROADMAP_v3.md
**Status:** Ready to Execute

---

## Executive Summary

Phases 1.5 and 2 establish safety infrastructure and execute high-risk modularization of create_pdf.py (10,184 lines). All recommendations from technical assessment integrated into approved roadmap v3.

**Total Duration:** 2-3 weeks
**Risk Level:** Medium (mitigated by rollback plan)
**Automation:** MonkeyType, Bowler/libcst pre-allocated

---

## Phase 1.5: Rollback Safety & Baselines

### Objective
Establish recovery capability and performance baseline before refactoring.

### Tasks & Ownership

**Task 1.5.1: Version Control Safety**
- **Owner:** Cascade
- **Actions:**
  - Tag current main as `v1.0-pre-refactor`
  - Create feature branch `refactor/phase-2-code-quality`
  - Lock tag to prevent accidental changes
- **Validation:** Tag exists, branch created, main protected
- **Duration:** 15 minutes

**Task 1.5.2: Rollback Documentation**
- **Owner:** Cascade
- **Actions:**
  - Create `/docs/ROLLBACK.md`
  - Document database restore procedure
  - Document asset restore procedure
  - Document code rollback steps
  - Test rollback procedure (dry run)
- **Validation:** ROLLBACK.md complete, procedure tested
- **Duration:** 2 hours

**Task 1.5.3: Benchmark Suite Creation**
- **Owner:** Cascade
- **Actions:**
  - Create `/tests/benchmarks/` directory
  - Implement benchmark for deck import (MTGA format)
  - Implement benchmark for token expansion
  - Implement benchmark for PDF generation
  - Implement benchmark for image fetch
  - Add memory profiling with tracemalloc
- **Validation:** All benchmarks run successfully
- **Duration:** 4-6 hours

**Task 1.5.4: Baseline Measurement**
- **Owner:** Cascade
- **Actions:**
  - Run benchmark suite on current codebase
  - Generate `benchmarks/baseline.json`
  - Commit baseline to repository
  - Document system configuration (Python version, OS, hardware)
- **Validation:** baseline.json committed, reproducible
- **Duration:** 1 hour

### Acceptance Criteria

**PASS Conditions:**
- [REQUIRED] Tag `v1.0-pre-refactor` exists and locked
- [REQUIRED] Branch `refactor/phase-2-code-quality` created
- [REQUIRED] `/docs/ROLLBACK.md` complete with tested procedure
- [REQUIRED] Benchmark suite runs without errors
- [REQUIRED] `benchmarks/baseline.json` committed to repo
- [REQUIRED] Baseline reproducible on local machine
- [REQUIRED] All current tests passing (62 tests)

**FAIL Conditions:**
- Any benchmark fails to run
- Baseline not reproducible
- Rollback procedure untested
- Tag not locked

### Rollback Validation Checkpoints

**Checkpoint 1.5.A: Tag Verification**
- **When:** After Task 1.5.1
- **Validation:** `git tag -l v1.0-pre-refactor` returns tag
- **Rollback Test:** `git checkout v1.0-pre-refactor` works

**Checkpoint 1.5.B: Benchmark Reproducibility**
- **When:** After Task 1.5.4
- **Validation:** Run benchmarks twice, results within 5% variance
- **Rollback Test:** Benchmarks run on tagged version

**Checkpoint 1.5.C: Documentation Completeness**
- **When:** After Task 1.5.2
- **Validation:** ROLLBACK.md includes all steps
- **Rollback Test:** Follow procedure in test environment

### Deliverables

1. Git tag: `v1.0-pre-refactor`
2. Feature branch: `refactor/phase-2-code-quality`
3. Documentation: `/docs/ROLLBACK.md`
4. Benchmark suite: `/tests/benchmarks/`
5. Baseline data: `benchmarks/baseline.json`
6. Phase summary: `mds/PHASE_1.5_SUMMARY.md`

### Estimated Effort
**Total:** 7-9 hours (1 week calendar time)

---

## Phase 2: Code Quality & Refactor

### Objective
Modularize create_pdf.py, expand type coverage, unify error handling, establish CI.

### Tasks & Ownership

**Task 2.1: Code Splitting - Pure Functions**
- **Owner:** Cascade
- **Actions:**
  - Use AST analysis to identify pure functions (no side effects)
  - Extract to `pdf/utils.py` first (lowest risk)
  - Update imports in create_pdf.py
  - Run test suite after extraction
  - Commit: "refactor: extract pure functions to pdf/utils.py"
- **Validation:** All 62 tests pass, no behavior changes
- **Duration:** 4-6 hours
- **Rollback:** Revert single commit

**Task 2.2: Code Splitting - Layout Module**
- **Owner:** Cascade
- **Actions:**
  - Extract layout functions to `pdf/layout.py`
  - Functions: card positioning, grid calculation, margin handling
  - Add backward compatibility imports in create_pdf.py
  - Run test suite
  - Commit: "refactor: extract layout logic to pdf/layout.py"
- **Validation:** All tests pass, imports work
- **Duration:** 4-6 hours
- **Rollback:** Revert single commit

**Task 2.3: Code Splitting - Render Module**
- **Owner:** Cascade
- **Actions:**
  - Extract rendering functions to `pdf/render.py`
  - Functions: PDF generation, image placement, text rendering
  - Add backward compatibility imports
  - Run test suite
  - Commit: "refactor: extract rendering to pdf/render.py"
- **Validation:** All tests pass
- **Duration:** 4-6 hours
- **Rollback:** Revert single commit

**Task 2.4: Code Splitting - Assets Module**
- **Owner:** Cascade
- **Actions:**
  - Extract asset management to `pdf/assets.py`
  - Functions: image loading, caching, validation
  - Add backward compatibility imports
  - Run test suite
  - Commit: "refactor: extract asset management to pdf/assets.py"
- **Validation:** All tests pass
- **Duration:** 4-6 hours
- **Rollback:** Revert single commit

**Task 2.5: Code Splitting - Deck Parser**
- **Owner:** Cascade
- **Actions:**
  - Extract deck parsing to `deck/parser.py`
  - Functions: format detection, line parsing, validation
  - Add backward compatibility imports
  - Run test suite
  - Commit: "refactor: extract deck parsing to deck/parser.py"
- **Validation:** All tests pass, all formats work
- **Duration:** 4-6 hours
- **Rollback:** Revert single commit

**Task 2.6: Type Hints - New Modules**
- **Owner:** Cascade
- **Actions:**
  - Run MonkeyType on test suite to generate stubs
  - Apply type hints to `pdf/`, `deck/` modules
  - Run mypy on new modules
  - Fix type errors
  - Add `# type: ignore` with tickets for deferred work
  - Commit: "feat: add type hints to pdf/ and deck/ modules"
- **Validation:** mypy passes on new modules
- **Duration:** 6-8 hours
- **Rollback:** Revert single commit

**Task 2.7: Type Hints - Existing Modules**
- **Owner:** Cascade
- **Actions:**
  - Apply type hints to `net/`, `db/`, `tools/` modules
  - Run mypy, fix errors
  - Commit per module
- **Validation:** mypy passes on all typed modules
- **Duration:** 4-6 hours
- **Rollback:** Revert commits

**Task 2.8: Error Handling - Define Hierarchy**
- **Owner:** Cascade
- **Actions:**
  - Create `errors.py` with ProxyError base class
  - Define subclasses: NetworkError, DatabaseError, ValidationError, PDFError
  - Add compatibility shims (inherit from existing exceptions)
  - Document error hierarchy in docstrings
  - Commit: "feat: add ProxyError exception hierarchy"
- **Validation:** Imports work, hierarchy documented
- **Duration:** 2-3 hours
- **Rollback:** Revert single commit

**Task 2.9: Error Handling - Migration**
- **Owner:** Cascade
- **Actions:**
  - Use libcst to find all exception sites
  - Replace generic exceptions in new modules first
  - Replace incrementally in touched files
  - Test after each batch (10-20 sites)
  - Commit per batch
- **Validation:** All error paths tested, no silent failures
- **Duration:** 4-6 hours
- **Rollback:** Revert commits

**Task 2.10: Test Observability**
- **Owner:** Cascade
- **Actions:**
  - Add pytest.ini with coverage, durations config
  - Configure coverage threshold (70% for new code)
  - Generate coverage report in CI
  - Add coverage badge to README.md
  - Commit: "feat: add test coverage and duration reporting"
- **Validation:** Coverage report generated, badge displays
- **Duration:** 2-3 hours
- **Rollback:** Revert single commit

**Task 2.11: CI Implementation**
- **Owner:** Cascade
- **Actions:**
  - Create `.github/workflows/test.yml`
  - Add job: syntax check (ruff)
  - Add job: test suite (pytest)
  - Add job: type check (mypy on typed modules)
  - Add job: benchmark comparison (fail if >5% regression)
  - Configure branch protection on main
  - Test on PR
  - Commit: "ci: add GitHub Actions workflow"
- **Validation:** CI runs successfully, all checks pass
- **Duration:** 4-6 hours
- **Rollback:** Delete workflow file

### Acceptance Criteria

**PASS Conditions:**
- [REQUIRED] All 62+ tests pass
- [REQUIRED] mypy clean on new modules (pdf/, deck/, net/, db/, tools/)
- [REQUIRED] No performance regression >5% (benchmark comparison)
- [REQUIRED] CI green on feature branch
- [REQUIRED] Coverage ≥70% on new code
- [REQUIRED] All commits follow conventional commits format
- [REQUIRED] Backward compatibility maintained (all CLI commands work)

**FAIL Conditions:**
- Any test fails
- Performance regression >5%
- mypy errors on typed modules
- CI fails
- Breaking changes to CLI

### Rollback Validation Checkpoints

**Checkpoint 2.A: After Each Module Split**
- **When:** After Tasks 2.1-2.5 (each)
- **Validation:**
  - All tests pass
  - No new warnings
  - Imports work from create_pdf.py
- **Rollback Test:** Revert commit, verify tests still pass

**Checkpoint 2.B: After Type Hints**
- **When:** After Tasks 2.6-2.7
- **Validation:**
  - mypy passes on typed modules
  - No runtime errors
  - Tests pass
- **Rollback Test:** Revert type hint commits, verify functionality

**Checkpoint 2.C: After Error Handling**
- **When:** After Tasks 2.8-2.9
- **Validation:**
  - All error paths tested
  - No silent failures
  - Error messages clear
- **Rollback Test:** Revert error handling commits, verify errors still caught

**Checkpoint 2.D: Before CI Merge**
- **When:** After Task 2.11
- **Validation:**
  - CI passes on feature branch
  - Benchmark comparison shows <5% change
  - All acceptance criteria met
- **Rollback Test:** Verify can rollback to v1.0-pre-refactor tag

### Performance Benchmarks

**Benchmark Ownership:**
- **Owner:** Cascade
- **Frequency:** After each major task (2.1-2.5, 2.6-2.7, 2.8-2.9)
- **Threshold:** ±5% from baseline
- **Action on Failure:** Investigate, optimize, or rollback

**Benchmarks to Track:**
1. **Deck Import:** Time to parse 60-card MTGA deck
2. **Token Expansion:** Time to resolve tokens for 20 cards
3. **PDF Generation:** Time to generate 9-card PDF
4. **Image Fetch:** Time to download 10 card images
5. **Memory Peak:** Peak memory during PDF generation

**Baseline Values (from Phase 1.5):**
- Recorded in `benchmarks/baseline.json`
- System configuration documented
- Reproducible on local machine

**Regression Handling:**
- >5% regression: STOP, investigate
- 3-5% regression: Document, create optimization ticket
- <3% regression: Acceptable variance

### Deliverables

1. Modules: `pdf/layout.py`, `pdf/render.py`, `pdf/assets.py`, `pdf/utils.py`
2. Modules: `deck/parser.py`
3. Error hierarchy: `errors.py`
4. CI workflow: `.github/workflows/test.yml`
5. Documentation: `pytest.ini`, coverage config
6. Benchmark comparison: `benchmarks/post-refactor.json`
7. Phase summary: `mds/PHASE_2_SUMMARY.md`

### Estimated Effort
**Total:** 34-50 hours (1-2 weeks calendar time)

---

## Automation Integration

### Pre-Allocated Tools

**Location:** `/automation/`

**Tool 1: MonkeyType (Type Inference)**
- **Purpose:** Generate type stubs from test execution
- **Usage:** `make automation-types`
- **Input:** Test suite execution traces
- **Output:** `.pyi` stub files
- **Integration:** Task 2.6, 2.7
- **Time Savings:** 60-70% (5-8 hours saved)

**Tool 2: Bowler/libcst (AST Refactoring)**
- **Purpose:** Automated code transformations
- **Usage:** `make automation-refactor`
- **Input:** Transformation rules
- **Output:** Modified Python files
- **Integration:** Task 2.1-2.5 (function extraction)
- **Time Savings:** 40-50% (8-12 hours saved)

**Tool 3: libcst (Exception Migration)**
- **Purpose:** Replace exception types systematically
- **Usage:** `make automation-errors`
- **Input:** Exception mapping rules
- **Output:** Modified exception sites
- **Integration:** Task 2.9
- **Time Savings:** 50-60% (3-5 hours saved)

### Automation Workflow

**Step 1: Generate Type Stubs**
```bash
# Run MonkeyType on test suite
make automation-types

# Review generated stubs
# Apply to modules
# Run mypy to validate
```

**Step 2: AST-Assisted Code Splitting**
```bash
# Analyze function dependencies
make automation-analyze

# Generate module structure
# Review proposed splits
# Apply transformations
# Run tests
```

**Step 3: Exception Migration**
```bash
# Find all exception sites
make automation-find-exceptions

# Generate migration plan
# Review changes
# Apply transformations
# Run tests
```

---

## Risk Mitigation Strategy

### High-Risk Areas

**Risk 1: create_pdf.py Modularization**
- **Severity:** HIGH
- **Mitigation:**
  - One module per commit
  - Test after each change
  - Maintain backward compatibility imports
  - Rollback checkpoint after each module
- **Escape Hatch:** Revert to v1.0-pre-refactor tag

**Risk 2: Type Hint Introduction**
- **Severity:** MEDIUM
- **Mitigation:**
  - New modules only (not legacy code)
  - Use MonkeyType for inference
  - Add type: ignore with tickets for deferred work
  - Gradual rollout
- **Escape Hatch:** Revert type hint commits

**Risk 3: Error Handling Changes**
- **Severity:** MEDIUM
- **Mitigation:**
  - Compatibility shims (ProxyError inherits from existing)
  - Incremental migration
  - Test all error paths
  - Document breaking changes
- **Escape Hatch:** Revert error handling commits

### Rollback Triggers

**Immediate Rollback If:**
- Test suite fails after change
- Performance regression >10%
- Breaking change to CLI
- Data corruption detected
- Unrecoverable error state

**Investigation Required If:**
- Performance regression 5-10%
- New warnings appear
- Coverage drops
- CI flaky

**Acceptable If:**
- Performance variance <5%
- New tests added (coverage increases)
- Warnings addressed with tickets

---

## Communication & Checkpoints

### Progress Reporting

**Daily Updates:**
- Task completion status
- Test results
- Benchmark results
- Blockers/issues

**Checkpoint Reviews:**
- After each major task
- Before merging to main
- Weekly sync (if multi-week)

### Checkpoint Schedule

**Week 1:**
- Day 1: Phase 1.5 complete (Checkpoint 1.5.C)
- Day 2-3: Tasks 2.1-2.3 (Checkpoints 2.A)
- Day 4-5: Tasks 2.4-2.5 (Checkpoints 2.A)

**Week 2:**
- Day 1-2: Tasks 2.6-2.7 (Checkpoint 2.B)
- Day 3: Tasks 2.8-2.9 (Checkpoint 2.C)
- Day 4: Tasks 2.10-2.11 (Checkpoint 2.D)
- Day 5: Phase 2 summary, merge preparation

### Human Review Points

**Required Human Approval:**
1. Phase 1.5 complete (before starting Phase 2)
2. Code splitting complete (before type hints)
3. All Phase 2 tasks complete (before merge to main)

**Optional Human Review:**
- After each module split (if requested)
- On performance regression (3-5%)
- On scope changes

---

## Success Metrics

### Phase 1.5 Success

- [METRIC] Tag created and locked
- [METRIC] Rollback procedure tested successfully
- [METRIC] Benchmark suite runs in <5 minutes
- [METRIC] Baseline reproducible (variance <5%)

### Phase 2 Success

- [METRIC] create_pdf.py reduced from 10,184 to <5,000 lines
- [METRIC] 5 new modules created (pdf/, deck/)
- [METRIC] Type coverage: 100% on new modules
- [METRIC] Error handling: ProxyError used in 80%+ of new code
- [METRIC] CI: All checks passing
- [METRIC] Performance: Within ±5% of baseline
- [METRIC] Tests: All 62+ passing, coverage ≥70%

### Quality Gates

**Gate 1: Code Quality**
- ruff passes (no linting errors)
- mypy passes on typed modules
- No TODO/FIXME without tickets

**Gate 2: Test Quality**
- All tests pass
- Coverage ≥70% on new code
- No skipped tests without reason

**Gate 3: Performance**
- Benchmarks within ±5% of baseline
- Memory usage not increased >10%
- No new performance warnings

**Gate 4: Documentation**
- All new modules have docstrings
- ROLLBACK.md complete
- Phase summary written

---

## Execution Confirmation

### Pre-Flight Checklist

- [CONFIRM] Approved roadmap v3 reviewed
- [CONFIRM] Automation tools pre-allocated in /automation/
- [CONFIRM] Current test suite passing (62 tests)
- [CONFIRM] Database backup available
- [CONFIRM] Rollback procedure understood
- [CONFIRM] Benchmark ownership assigned (Cascade)
- [CONFIRM] Performance thresholds defined (±5%)
- [CONFIRM] Communication schedule established

### Ready to Execute

**Phase 1.5 Start:** Upon approval
**Phase 2 Start:** After Phase 1.5 checkpoint 1.5.C passes
**Estimated Completion:** 2-3 weeks from start

### Approval Required

**Awaiting approval from:** Patrick Hart
**Approval confirms:**
- Benchmark ownership: Cascade
- Rollback validation checkpoints: Defined and approved
- Performance thresholds: ±5% acceptable
- Execution plan: Approved to proceed

---

**Prepared by:** Cascade (Claude Sonnet 4.5)
**Date:** 2025-10-16
**Status:** READY FOR APPROVAL
