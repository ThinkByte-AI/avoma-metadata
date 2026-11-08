"""Text embeddings: Bedrock Titan v2 in production, a deterministic fake for tests and dev-mock mode."""
import hashlib
import json
import logging
import math
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Any, Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import (
    ClientError,
    ConnectionClosedError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)

log = logging.getLogger("app.ai.embeddings")

_RETRYABLE = {"ThrottlingException", "ServiceUnavailableException", "ModelNotReadyException", "InternalServerException"}
_NETWORK_ERRORS = (ReadTimeoutError, ConnectTimeoutError, EndpointConnectionError, ConnectionClosedError)


class Embedder(Protocol):
    dim: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class FakeEmbedder:
    """Bag-of-words hashed into `dim` buckets, L2-normalised. Similar wording → similar vectors."""

    def __init__(self, dim: int = 512):
        self.dim = dim

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for tok in re.findall(r"[a-z0-9]+", text.lower()):
            idx = int.from_bytes(hashlib.blake2b(tok.encode(), digest_size=4).digest(), "big") % self.dim
            v[idx] += 1.0
        norm = math.sqrt(sum(x * x for x in v))
        if norm == 0:
            v[0] = 1.0
            return v
        return [x / norm for x in v]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


class BedrockEmbedder:
    def __init__(
        self,
        model_id: str,
        region: str,
        dim: int,
        concurrency: int = 16,
        client: Any = None,
        max_retries: int = 5,
        backoff_base: float = 0.5,
    ):
        self.model_id, self.dim, self.concurrency = model_id, dim, max(1, concurrency)
        self.max_retries, self.backoff_base = max_retries, backoff_base
        self.client = client or boto3.client(
            "bedrock-runtime",
            region_name=region,
            config=Config(retries={"mode": "adaptive", "max_attempts": 6}, max_pool_connections=max(10, concurrency),
                          connect_timeout=10, read_timeout=30),
        )

    def _one(self, text: str) -> list[float]:
        body = json.dumps({"inputText": text, "dimensions": self.dim, "normalize": True})
        for attempt in range(self.max_retries + 1):
            try:
                r = self.client.invoke_model(
                    modelId=self.model_id, body=body, contentType="application/json", accept="application/json"
                )
                return json.loads(r["body"].read())["embedding"]
            except ClientError as e:
                code = e.response.get("Error", {}).get("Code", "")
                if code not in _RETRYABLE or attempt == self.max_retries:
                    raise
            except _NETWORK_ERRORS:
                if attempt == self.max_retries:
                    raise
            time.sleep(self.backoff_base * (2**attempt) * (0.5 + random.random()))
        raise RuntimeError("unreachable")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self.concurrency == 1 or len(texts) <= 1:
            return [self._one(t) for t in texts]
        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            return list(pool.map(self._one, texts))

    def embed_query(self, text: str) -> list[float]:
        return self._one(text)


@lru_cache
def get_query_embedder() -> Embedder:
    """FastAPI dependency: one shared embedder for search queries."""
    from app.config import get_settings  # noqa: PLC0415

    return get_embedder(get_settings())


def get_embedder(settings) -> Embedder:
    if settings.app_mode == "dev-mock":
        return FakeEmbedder(settings.embed_dim)
    return BedrockEmbedder(
        settings.bedrock_embed_model, settings.aws_region, settings.embed_dim, settings.embed_concurrency
    )
