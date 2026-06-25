# Quality Gates Modularization v2.3.5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the assessment follow-up items for stronger quality gates and hotspot modularization, then release Sagitta Control customer deployment version v2.3.5.

**Architecture:** Keep behavior unchanged while tightening existing gates. Extract stable commercial UI constants/helpers into a focused module so `CommercialOpsPage.tsx` remains a page coordinator rather than a mixed configuration and rendering file.

**Tech Stack:** Python 3.12, FastAPI, pytest, mypy, React 18, TypeScript, Vite, Vitest, Ant Design, GitHub Actions, Docker Compose.

---

### Task 1: Raise Quality Gates

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `README.md`
- Modify: `backend/mypy-baseline.txt`

- [ ] **Step 1: Verify current coverage can support 55%**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/unit -q --cov=app --cov-report=term-missing --cov-fail-under=55
```

Expected: passes with total coverage at least 55%.

- [ ] **Step 2: Expand mypy baseline with already-clean modules**

Add these exact lines to `backend/mypy-baseline.txt` in sorted logical locations:

```text
app/core/security.py
app/services/commercial_ops_metadata.py
```

- [ ] **Step 3: Raise CI coverage gate**

Change the backend unit test command in `.github/workflows/ci.yml` from:

```yaml
run: pytest tests/unit/ -v --cov=app --cov-fail-under=45
```

to:

```yaml
run: pytest tests/unit/ -v --cov=app --cov-fail-under=55
```

- [ ] **Step 4: Update README quality wording**

Change README backend command and quality-gate paragraph so the documented coverage gate is `55%`, and note that the current next target is incremental module-level strengthening rather than the old 45-to-55 plan.

- [ ] **Step 5: Verify mypy baseline**

Run:

```bash
cd backend
while IFS= read -r target; do
  mypy --follow-imports=silent "$target"
done < mypy-baseline.txt
```

Expected: all listed files pass.

### Task 2: Split Commercial Operations Page Hotspot

**Files:**
- Create: `frontend/src/pages/commercial/commercialOpsConfig.tsx`
- Modify: `frontend/src/pages/commercial/CommercialOpsPage.tsx`
- Test: `frontend/src/pages/commercial/CommercialOpsPage.test.tsx`

- [ ] **Step 1: Run current page test as red/green baseline**

Run:

```bash
cd frontend
npm run test -- CommercialOpsPage.test.tsx
```

Expected: current tests pass before refactor.

- [ ] **Step 2: Extract commercial page static config**

Move `reportTypes`, status color/label maps, `supportLevelColor`, and `nowrapText` from `CommercialOpsPage.tsx` into `commercialOpsConfig.tsx`.

- [ ] **Step 3: Import extracted config from page**

Update `CommercialOpsPage.tsx` to import the extracted constants/helpers and remove the inline definitions.

- [ ] **Step 4: Verify commercial page behavior**

Run:

```bash
cd frontend
npm run test -- CommercialOpsPage.test.tsx
```

Expected: tests pass.

### Task 3: Version v2.3.5 and Customer Package

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/main.py`
- Modify: `backend/app/services/commercial_ops_metadata.py`
- Modify: `backend/app/data/commercial_delivery_manifest.json`
- Modify: `backend/tests/integration/test_health.py`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Modify: `.github/workflows/commercial-release.yml`
- Modify: `.github/workflows/release-version-record.yml`
- Modify: `README.md`
- Modify: `docs/*.md` version references that describe the current commercial deployment version.

- [ ] **Step 1: Update source and docs versions**

Replace current product version references from `2.3.0` to `2.3.5` in source version constants, package metadata, health tests, release workflow base version, and current-version docs. Do not replace unrelated dependency versions such as `iniconfig==2.3.0`.

- [ ] **Step 2: Verify health version test**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/integration/test_health.py -q
```

Expected: test expects and receives `2.3.5`.

- [ ] **Step 3: Generate customer deployment package**

Run:

```bash
python3 scripts/render-customer-package.py \
  --version 2.3.5 \
  --image-repository ghcr.io/lynn-lee/sagitta-control \
  --output-dir dist-commercial \
  --package-name Sagitta-Control-v2.3.5
```

Expected: `dist-commercial/Sagitta-Control-v2.3.5.zip` and `.sha256` are created and pass checksum verification.

### Task 4: Full Verification, Publish, and ECS Sync

**Files:**
- No new source files expected beyond earlier tasks.

- [ ] **Step 1: Run focused backend checks**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/unit -q --cov=app --cov-fail-under=55
backend/.venv/bin/python -m pytest backend/tests/integration/test_health.py -q
```

Expected: both pass.

- [ ] **Step 2: Run focused frontend checks**

Run:

```bash
cd frontend
npm run test -- CommercialOpsPage.test.tsx
npm run build
```

Expected: both pass.

- [ ] **Step 3: Commit, push, and tag**

Create a commit for the quality/modularization/release version work, push `main` to `origin` and `gitee`, create tag `v2.3.5`, and push the tag to `origin`.

- [ ] **Step 4: Verify release outputs**

Check GitHub Actions for `CI`, `Release Version Record`, and commercial release. Verify `Lynn-Lee/Sagitta-Deploy` release `v2.3.5` and expected package assets if the tag release workflow completes.

- [ ] **Step 5: Force ECS source-test refresh**

Run on ECS:

```bash
cd /opt/sagitta-control/source
COMPOSE_PROJECT_NAME=sagitta-control-source-test bash deploy/update-prod.sh --full
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1/health
```

Expected: backend and frontend health return version `2.3.5`.
