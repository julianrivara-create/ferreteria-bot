from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .logging_config import logger
from .persistence import mark_dependency_failure, mark_dependency_success, read_dependency_state
from .types import DEPENDENCY_DOMAINS

RAILWAY_API_URL = "https://backboard.railway.app/graphql/v2"


class RailwayDependencyError(Exception):
    def __init__(self, domain: str, message: str, *, http_status: int | None = None, error_code: str | None = None):
        super().__init__(message)
        self.domain = domain
        self.message = message
        self.http_status = http_status
        self.error_code = error_code or "RAILWAY_DEPENDENCY_ERROR"

    def to_payload(self, circuit_open_until: datetime | None = None) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "http_status": self.http_status,
            "error_code": self.error_code,
            "message": self.message,
            "circuit_open_until": circuit_open_until.isoformat() if circuit_open_until else None,
        }


class RailwayClient:
    def __init__(self, api_token: str | None, dependency_cfg: dict[str, Any] | None = None):
        self.api_token = (api_token or "").strip()
        dependency_cfg = dependency_cfg or {}
        self.fail_threshold = int(dependency_cfg.get("dependency_circuit_fail_threshold", 3))
        self.open_minutes = int(dependency_cfg.get("dependency_circuit_open_minutes", 15))

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    def _check_domain(self, domain: str) -> None:
        if domain not in DEPENDENCY_DOMAINS:
            raise ValueError(f"Unsupported dependency domain: {domain}")

    def _is_dependency_failure(self, http_status: int | None, errors: list[dict[str, Any]] | None = None) -> bool:
        if http_status is None:
            return True
        if http_status in {401, 403, 429}:
            return True
        if http_status >= 500:
            return True
        if errors:
            return True
        return False

    def _is_circuit_open(self, conn, tenant_id: str, service_id: str, domain: str) -> datetime | None:
        state = read_dependency_state(conn, tenant_id, service_id, domain)
        open_until = state.get("circuit_open_until")
        if not open_until:
            return None
        now = datetime.now(timezone.utc)
        if open_until.tzinfo is None:
            open_until = open_until.replace(tzinfo=timezone.utc)
        if open_until > now:
            return open_until
        return None

    async def _request(
        self,
        conn,
        *,
        tenant_id: str,
        service_id: str,
        domain: str,
        query: str,
        variables: dict[str, Any],
    ) -> dict[str, Any]:
        self._check_domain(domain)

        if not self.api_token:
            err = RailwayDependencyError(domain, "RAILWAY_API_TOKEN missing", error_code="MISSING_TOKEN")
            state = mark_dependency_failure(
                conn,
                tenant_id=tenant_id,
                service_id=service_id,
                domain=domain,
                threshold=self.fail_threshold,
                open_minutes=self.open_minutes,
                error_payload=err.to_payload(),
            )
            raise RailwayDependencyError(domain, err.message, error_code=err.error_code).with_traceback(None)

        open_until = self._is_circuit_open(conn, tenant_id, service_id, domain)
        if open_until:
            raise RailwayDependencyError(
                domain,
                f"Circuit breaker open for {domain}",
                error_code="CIRCUIT_OPEN",
            )

        payload = {"query": query, "variables": variables}
        backoff = [0.2, 0.6, 1.8]
        last_error: RailwayDependencyError | None = None

        async with httpx.AsyncClient(timeout=20) as client:
            for idx, delay in enumerate(backoff, start=1):
                try:
                    resp = await client.post(RAILWAY_API_URL, headers=self._headers(), json=payload)
                    body = resp.json() if resp.content else {}
                except Exception as exc:
                    last_error = RailwayDependencyError(domain, f"Railway request failed: {exc}", error_code="NETWORK_ERROR")
                else:
                    errors = body.get("errors") if isinstance(body, dict) else None
                    if resp.status_code == 200 and not errors:
                        mark_dependency_success(conn, tenant_id, service_id, domain)
                        return body
                    if self._is_dependency_failure(resp.status_code, errors):
                        msg = errors[0].get("message") if errors else f"HTTP {resp.status_code}"
                        last_error = RailwayDependencyError(
                            domain,
                            f"Railway dependency failure: {msg}",
                            http_status=resp.status_code,
                            error_code="GRAPHQL_ERROR" if errors else "HTTP_ERROR",
                        )
                    else:
                        # Validation/business errors should not open dependency breaker.
                        return body

                if idx < len(backoff):
                    await asyncio.sleep(delay)

        assert last_error is not None
        state = mark_dependency_failure(
            conn,
            tenant_id=tenant_id,
            service_id=service_id,
            domain=domain,
            threshold=self.fail_threshold,
            open_minutes=self.open_minutes,
            error_payload=last_error.to_payload(),
        )
        raise RailwayDependencyError(
            domain,
            last_error.message,
            http_status=last_error.http_status,
            error_code=last_error.error_code,
        )

    async def latest_deployment_id(self, conn, *, tenant_id: str, service_id: str) -> str | None:
        body = await self._request(
            conn,
            tenant_id=tenant_id,
            service_id=service_id,
            domain="railway_deployments",
            query="""
                query LatestDeployment($serviceId: String!) {
                  deployments(first: 1, input: { serviceId: $serviceId }) {
                    edges { node { id status createdAt } }
                  }
                }
            """,
            variables={"serviceId": service_id},
        )
        edges = body.get("data", {}).get("deployments", {}).get("edges", []) if isinstance(body, dict) else []
        if not edges:
            return None
        node = edges[0].get("node") if isinstance(edges[0], dict) else None
        if not isinstance(node, dict):
            return None
        return node.get("id")

    async def deployment_logs(
        self,
        conn,
        *,
        tenant_id: str,
        service_id: str,
        lookback_hours: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        deployment_id = await self.latest_deployment_id(conn, tenant_id=tenant_id, service_id=service_id)
        if not deployment_id:
            return []
        start_date = (datetime.now(timezone.utc) - timedelta(hours=max(1, int(lookback_hours)))).isoformat().replace("+00:00", "Z")
        body = await self._request(
            conn,
            tenant_id=tenant_id,
            service_id=service_id,
            domain="railway_logs",
            query="""
                query DeploymentLogs($deploymentId: String!, $limit: Int!, $startDate: DateTime) {
                  deploymentLogs(deploymentId: $deploymentId, limit: $limit, startDate: $startDate) {
                    message
                    timestamp
                    severity
                  }
                }
            """,
            variables={"deploymentId": deployment_id, "limit": int(limit), "startDate": start_date},
        )
        items = body.get("data", {}).get("deploymentLogs", []) if isinstance(body, dict) else []
        if not isinstance(items, list):
            return []
        out = []
        for item in items:
            if not isinstance(item, dict):
                continue
            out.append(
                {
                    "message": str(item.get("message", "")),
                    "timestamp": str(item.get("timestamp", "")),
                    "severity": str(item.get("severity", "INFO")).upper(),
                }
            )
        return out

    async def metrics(
        self,
        conn,
        *,
        tenant_id: str,
        service_id: str,
        start_date: datetime,
        end_date: datetime,
        sample_rate_seconds: int,
        measurements: list[str],
    ) -> list[dict[str, Any]]:
        body = await self._request(
            conn,
            tenant_id=tenant_id,
            service_id=service_id,
            domain="railway_metrics",
            query="""
                query Metrics(
                  $serviceId: String!,
                  $startDate: DateTime!,
                  $endDate: DateTime!,
                  $sampleRateSeconds: Int!,
                  $measurements: [MetricMeasurement!]!
                ) {
                  metrics(
                    serviceId: $serviceId,
                    startDate: $startDate,
                    endDate: $endDate,
                    sampleRateSeconds: $sampleRateSeconds,
                    measurements: $measurements
                  ) {
                    measurement
                    values { ts value }
                  }
                }
            """,
            variables={
                "serviceId": service_id,
                "startDate": start_date.isoformat().replace("+00:00", "Z"),
                "endDate": end_date.isoformat().replace("+00:00", "Z"),
                "sampleRateSeconds": int(sample_rate_seconds),
                "measurements": measurements,
            },
        )
        rows = body.get("data", {}).get("metrics", []) if isinstance(body, dict) else []
        if not isinstance(rows, list):
            return []
        return rows

    async def deployment_restart(self, conn, *, tenant_id: str, service_id: str, deployment_id: str) -> bool:
        body = await self._request(
            conn,
            tenant_id=tenant_id,
            service_id=service_id,
            domain="railway_deployments",
            query="""
                mutation Restart($id: String!) {
                  deploymentRestart(id: $id)
                }
            """,
            variables={"id": deployment_id},
        )
        return bool(body.get("data", {}).get("deploymentRestart"))

    async def deployment_redeploy(self, conn, *, tenant_id: str, service_id: str, deployment_id: str) -> str | None:
        body = await self._request(
            conn,
            tenant_id=tenant_id,
            service_id=service_id,
            domain="railway_deployments",
            query="""
                mutation Redeploy($id: String!, $usePreviousImageTag: Boolean) {
                  deploymentRedeploy(id: $id, usePreviousImageTag: $usePreviousImageTag) {
                    id
                  }
                }
            """,
            variables={"id": deployment_id, "usePreviousImageTag": True},
        )
        node = body.get("data", {}).get("deploymentRedeploy", {}) if isinstance(body, dict) else {}
        if not isinstance(node, dict):
            return None
        return node.get("id")
