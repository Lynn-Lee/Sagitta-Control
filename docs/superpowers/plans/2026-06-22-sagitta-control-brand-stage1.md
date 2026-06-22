# Sagitta Control Brand Stage 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Switch the visible product brand to Sagitta Control Platform / 矢准数据库安全管控平台 while keeping the existing `sagitta-control` technical project code compatible.

**Architecture:** This stage changes customer-facing defaults, UI copy, API display names, and documentation. It deliberately leaves repository remotes, ECS paths, Docker image names, Helm chart directory names, historical commercial packages, and License project code unchanged.

**Tech Stack:** FastAPI, Python service tests, React/Vite/TypeScript, Vitest, Markdown documentation.

---

### File Map

- Modify: `frontend/src/api/branding.ts` for default platform display name.
- Modify: `frontend/src/pages/auth/LoginPage.tsx` for login-page brand slogan and footer.
- Modify: `frontend/src/components/layout/MainLayout.test.tsx` and `frontend/src/pages/auth/LoginPage.test.tsx` for UI brand assertions.
- Modify: `backend/app/main.py`, `backend/app/services/license.py`, `backend/app/services/system_config.py`, `backend/app/services/commercial_ops.py` for API title, default platform name, notification copy, License display name, and generated report titles.
- Modify: `backend/tests/unit/test_commercial_ops.py` and focused License/system config tests for backend display-name expectations while keeping `sagitta-control` project-code assertions.
- Modify: `README.md`, `docs/sagitta_control_prd.md`, `docs/public_commercial_delivery.md`, `docs/user_manual.md`, `docs/operations_guide.md`, `docs/commercial_promotion_copy.md`, `docs/commercial_product_manual.md`, `docs/commercial_ops_deployment_guide.md`, and `AGENT.md` for visible naming and migration boundary.

### Task 1: Frontend Brand Defaults

**Files:**
- Test: `frontend/src/components/layout/MainLayout.test.tsx`
- Test: `frontend/src/pages/auth/LoginPage.test.tsx`
- Modify: `frontend/src/api/branding.ts`
- Modify: `frontend/src/pages/auth/LoginPage.tsx`

- [ ] **Step 1: Update tests first**
  Assert the default brand is `Sagitta Control` and the login slogan is `Aim at Data, Govern with Precision`.
- [ ] **Step 2: Run focused frontend tests and verify they fail**
  Run: `cd frontend && npm run test -- MainLayout LoginPage --run`
  Expected: FAIL because implementation still renders `Sagitta Control` and `Control with Precision`.
- [ ] **Step 3: Update the frontend implementation**
  Change default `platform_name`, login slogan, footer product line, and user-facing monitoring help text.
- [ ] **Step 4: Run focused frontend tests and verify they pass**
  Run: `cd frontend && npm run test -- MainLayout LoginPage --run`
  Expected: PASS.

### Task 2: Backend Display Name Defaults

**Files:**
- Test: `backend/tests/unit/test_commercial_ops.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/services/license.py`
- Modify: `backend/app/services/system_config.py`
- Modify: `backend/app/services/commercial_ops.py`

- [ ] **Step 1: Update tests first**
  Assert generated commercial metadata and reports use `Sagitta Control`, while existing `project_code` remains `sagitta-control`.
- [ ] **Step 2: Run focused backend tests and verify they fail**
  Run: `cd backend && . .venv/bin/activate && pytest tests/unit/test_commercial_ops.py tests/unit/test_license_service.py tests/unit/test_system_config.py -q`
  Expected: FAIL where implementation still emits `Sagitta Control`.
- [ ] **Step 3: Update backend display-name implementation**
  Change `LICENSE_PROJECT_NAME`, FastAPI title/root message, default `platform_name`, and notification test copy. Do not change `LICENSE_PROJECT_CODE`.
- [ ] **Step 4: Run focused backend tests and verify they pass**
  Run: `cd backend && . .venv/bin/activate && pytest tests/unit/test_commercial_ops.py tests/unit/test_license_service.py tests/unit/test_system_config.py -q`
  Expected: PASS.

### Task 3: Documentation Stage-1 Rename

**Files:**
- Modify: `README.md`
- Modify: `docs/sagitta_control_prd.md`
- Modify: `docs/public_commercial_delivery.md`
- Modify: `docs/user_manual.md`
- Modify: `docs/operations_guide.md`
- Modify: `docs/commercial_promotion_copy.md`
- Modify: `docs/commercial_product_manual.md`
- Modify: `docs/commercial_ops_deployment_guide.md`
- Modify: `AGENT.md`

- [ ] **Step 1: Update public positioning**
  Replace visible product name with `Sagitta Control Platform` / `矢准数据库安全管控平台` where the text is product-facing.
- [ ] **Step 2: Preserve technical compatibility names**
  Keep `sagitta-control`, `Sagitta-Control`, existing Git remotes, `/opt/sagitta-control/source`, `deploy/helm/sagitta-control`, and historical package examples as compatibility notes unless the text describes next-version naming.
- [ ] **Step 3: Document the migration boundary**
  Add a clear note that stage 1 changes external product naming only and that technical identifiers remain compatible until a later migration.

### Task 4: Verification and Diff Review

**Files:**
- Verify all changed files.

- [ ] **Step 1: Run frontend build**
  Run: `cd frontend && npm run build`
  Expected: PASS.
- [ ] **Step 2: Run backend focused tests**
  Run: `cd backend && . .venv/bin/activate && pytest tests/unit/test_commercial_ops.py tests/unit/test_license_service.py tests/unit/test_system_config.py -q`
  Expected: PASS.
- [ ] **Step 3: Review remaining brand hits**
  Run: `rg -n "Sagitta Control|矢准数据库安全管控平台|Control with Precision" README.md docs AGENT.md frontend/src backend/app backend/tests`
  Expected: Remaining hits are either compatibility references, historical package/repo names, or intentionally preserved project codes.
- [ ] **Step 4: Inspect git diff**
  Run: `git status --short && git diff --stat`
  Expected: Only stage-1 brand and documentation files changed, plus the pre-existing `.gitignore` remains unrelated.
