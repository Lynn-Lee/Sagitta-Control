"""OpenSearch 引擎适配。

OpenSearch 与 Elasticsearch 在索引/分片/节点观测模型上接近，但运行时客户端、
SQL API 路径和产品校验边界不同，因此作为独立引擎注册。
"""

from __future__ import annotations

from typing import Any

from app.engines.elasticsearch import ElasticsearchEngine


class OpenSearchEngine(ElasticsearchEngine):
    name = "OpenSearchEngine"
    db_type = "opensearch"

    async def get_connection(self, db_name: str | None = None) -> Any:
        if self._client is None:
            try:
                from opensearchpy import AsyncOpenSearch
            except ImportError as exc:
                raise ImportError("pip install 'opensearch-py[async]'") from exc

            kwargs: dict[str, Any] = {
                "timeout": 10,
                "verify_certs": False,
                "ssl_show_warn": False,
            }
            if self._user or self._password:
                kwargs["http_auth"] = (self._user or "", self._password or "")
            self._client = AsyncOpenSearch([self._connection_url()], **kwargs)
        return self._client

    async def _sql_query(self, client: Any, payload: dict[str, Any]) -> Any:
        return await client.transport.perform_request("POST", "/_plugins/_sql", body=payload)
