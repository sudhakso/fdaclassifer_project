"""GCS download and directory upload used by the training job."""

from __future__ import annotations

import os

from google.cloud import storage


def parse_gcs_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("gs://"):
        raise ValueError(f"Expected a gs:// URI, got {uri!r}")
    rest = uri[5:]
    bucket_name, separator, blob_name = rest.partition("/")
    if not bucket_name or not separator or not blob_name:
        raise ValueError(f"GCS URI must include a bucket and object path: {uri!r}")
    return bucket_name, blob_name


def download_blob(gcs_uri: str, local_path: str) -> None:
    bucket_name, blob_name = parse_gcs_uri(gcs_uri)
    os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    bucket.blob(blob_name).download_to_filename(local_path)


def upload_directory(local_dir: str, gcs_uri: str) -> int:
    bucket_name, prefix = parse_gcs_uri(gcs_uri)
    prefix = prefix.rstrip("/")
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    uploaded = 0
    for root, _, files in os.walk(local_dir):
        for name in files:
            local_file_path = os.path.join(root, name)
            relative = os.path.relpath(local_file_path, local_dir)
            blob_path = f"{prefix}/{relative}"
            bucket.blob(blob_path).upload_from_filename(local_file_path)
            uploaded += 1
    return uploaded
