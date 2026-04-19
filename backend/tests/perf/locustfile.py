"""
SagittaDB 性能测试（Pack G P1）。

使用方式：
    # 安装：pip install locust
    # 交互式启动（Web UI）：
    locust -f tests/perf/locustfile.py --host http://localhost:8000

    # 无头压测（CI）：
    locust -f tests/perf/locustfile.py --host http://localhost:8000 \\
        --headless -u 50 -r 10 --run-time 60s \\
        --csv reports/perf

测试场景：
  - 登录接口（高频）
  - /auth/me 接口（已认证用户，高频）
  - 工单列表查询（中频）
  - 实例列表查询（中频）
  - 在线查询提交（低频，高耗时）
"""
from __future__ import annotations

import random

from locust import HttpUser, TaskSet, between, task

# ── 共享登录凭证 ──────────────────────────────────────────────

ADMIN_CREDENTIALS = {"username": "admin", "password": "Admin@2024!"}
RESET_ADMIN_PASSWORD = "AdminReset@2026"


def _login(client) -> str | None:
    """登录并返回 access_token，失败返回 None。"""
    with client.post(
        "/api/v1/auth/login/",
        json=ADMIN_CREDENTIALS,
        catch_response=True,
        name="POST /auth/login/",
    ) as resp:
        if resp.status_code == 200:
            data = resp.json()
            if data.get("password_change_required"):
                change_resp = client.post(
                    "/api/v1/auth/password/change-required/",
                    json={
                        "password_change_token": data.get("password_change_token"),
                        "new_password": RESET_ADMIN_PASSWORD,
                    },
                    name="POST /auth/password/change-required/",
                )
                if change_resp.status_code != 200:
                    resp.failure(f"Force password change failed: {change_resp.status_code}")
                    return None
                ADMIN_CREDENTIALS["password"] = RESET_ADMIN_PASSWORD
                return _login(client)
            return data.get("access_token")
        resp.failure(f"Login failed: {resp.status_code}")
        return None


# ── 任务集：认证流程 ──────────────────────────────────────────

class AuthTasks(TaskSet):
    token: str | None = None

    def on_start(self):
        self.token = _login(self.client)

    @task(5)
    def get_me(self):
        if not self.token:
            return
        with self.client.get(
            "/api/v1/auth/me/",
            headers={"Authorization": f"Bearer {self.token}"},
            catch_response=True,
            name="GET /auth/me/",
        ) as resp:
            if resp.status_code == 401:
                self.token = _login(self.client)
                resp.failure("token 过期，已刷新")
            elif resp.status_code != 200:
                resp.failure(f"Unexpected: {resp.status_code}")

    @task(2)
    def refresh_token(self):
        """模拟 token 刷新（低频）。"""
        # 先登录获取 refresh_token
        login_resp = self.client.post(
            "/api/v1/auth/login/",
            json=ADMIN_CREDENTIALS,
            name="POST /auth/login/ [refresh prep]",
        )
        if login_resp.status_code != 200:
            return
        refresh = login_resp.json().get("refresh_token", "")
        with self.client.post(
            "/api/v1/auth/token/refresh/",
            json={"refresh_token": refresh},
            catch_response=True,
            name="POST /auth/token/refresh/",
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"Refresh failed: {resp.status_code}")
            else:
                self.token = resp.json().get("access_token", self.token)


# ── 任务集：工单与实例查询 ────────────────────────────────────

class WorkloadTasks(TaskSet):
    token: str | None = None

    def on_start(self):
        self.token = _login(self.client)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    @task(4)
    def list_workflows(self):
        page = random.randint(1, 3)
        with self.client.get(
            f"/api/v1/workflows/?page={page}&page_size=20",
            headers=self._headers(),
            catch_response=True,
            name="GET /workflows/ [list]",
        ) as resp:
            if resp.status_code == 401:
                self.token = _login(self.client)
                resp.failure("token 过期")
            elif resp.status_code != 200:
                resp.failure(f"Unexpected: {resp.status_code}")

    @task(3)
    def list_instances(self):
        with self.client.get(
            "/api/v1/instances/?page_size=20",
            headers=self._headers(),
            catch_response=True,
            name="GET /instances/ [list]",
        ) as resp:
            if resp.status_code not in (200, 403):
                resp.failure(f"Unexpected: {resp.status_code}")

    @task(2)
    def list_masking_rules(self):
        with self.client.get(
            "/api/v1/masking/rules/?page_size=20",
            headers=self._headers(),
            catch_response=True,
            name="GET /masking/rules/ [list]",
        ) as resp:
            if resp.status_code not in (200, 403, 404):
                resp.failure(f"Unexpected: {resp.status_code}")

    @task(1)
    def get_dashboard_stats(self):
        with self.client.get(
            "/api/v1/monitor/dashboard/?days=7",
            headers=self._headers(),
            catch_response=True,
            name="GET /monitor/dashboard/",
        ) as resp:
            if resp.status_code not in (200, 403, 404):
                resp.failure(f"Unexpected: {resp.status_code}")


# ── 用户类 ────────────────────────────────────────────────────

class AuthUser(HttpUser):
    """专注于认证流程的虚拟用户（高频登录/token 操作）。"""
    tasks = [AuthTasks]
    wait_time = between(0.5, 2)
    weight = 3


class APIUser(HttpUser):
    """模拟正常业务操作的虚拟用户（工单 + 实例查询）。"""
    tasks = [WorkloadTasks]
    wait_time = between(1, 3)
    weight = 7
