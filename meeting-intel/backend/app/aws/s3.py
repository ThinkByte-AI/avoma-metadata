"""Read-only access to the archive bucket. This module never writes, copies or deletes objects."""
import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.config import get_settings


@dataclass(frozen=True)
class S3Object:
    key: str
    size: int
    etag: str
    storage_class: str
    last_modified: datetime


class S3Store:
    def __init__(self, bucket: str, region: str, client: Any = None):
        self.bucket = bucket
        self.region = region
        self.client = client or boto3.client(
            "s3",
            region_name=region,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "virtual"},
                retries={"mode": "adaptive", "max_attempts": 8},
            ),
        )

    def iter_objects(self, prefixes: list[str]) -> Iterator[S3Object]:
        paginator = self.client.get_paginator("list_objects_v2")
        for prefix in prefixes:
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                for o in page.get("Contents", []):
                    yield S3Object(
                        key=o["Key"],
                        size=int(o.get("Size", 0)),
                        etag=str(o.get("ETag", "")).strip('"'),
                        storage_class=o.get("StorageClass") or "STANDARD",
                        last_modified=o["LastModified"],
                    )

    def fetch(self, key: str) -> tuple[bytes, str]:
        """Return (body, etag). Only used for small text files (transcripts, notes)."""
        r = self.client.get_object(Bucket=self.bucket, Key=key)
        return r["Body"].read(), str(r.get("ETag", "")).strip('"')

    def get_json(self, key: str) -> Any:
        return json.loads(self.fetch(key)[0])

    def get_text(self, key: str) -> str:
        return self.fetch(key)[0].decode("utf-8", errors="replace")

    def presign_get(self, key: str, content_type: str, ttl: int, download_name: str | None = None) -> str:
        params = {"Bucket": self.bucket, "Key": key, "ResponseContentType": content_type}
        if download_name:
            params["ResponseContentDisposition"] = f'attachment; filename="{download_name}"'
        return self.client.generate_presigned_url("get_object", Params=params, ExpiresIn=ttl)

    def check(self) -> dict:
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return {"ok": True, "bucket": self.bucket, "region": self.region, "error": None}
        except (ClientError, BotoCoreError) as e:
            return {"ok": False, "bucket": self.bucket, "region": self.region, "error": str(e)}


def get_store() -> S3Store:
    """FastAPI dependency / factory built from settings."""
    s = get_settings()
    return S3Store(s.s3_bucket, s.aws_region)
