import json
import os
from typing import Optional

import firebase_admin
from firebase_admin import credentials, firestore, storage

_firestore_client: Optional[firestore.Client] = None
_storage_bucket: Optional[storage.bucket] = None
_app_initialized = False


def _init_firebase_app() -> None:
    global _app_initialized
    if _app_initialized:
        return

    project_id = os.getenv("FIREBASE_PROJECT_ID")
    service_account_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH")
    service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    bucket_name = os.getenv("FIREBASE_STORAGE_BUCKET")

    if not project_id or (not service_account_path and not service_account_json):
        raise RuntimeError(
            "Firebase is not configured. Set FIREBASE_PROJECT_ID and "
            "FIREBASE_SERVICE_ACCOUNT_PATH or FIREBASE_SERVICE_ACCOUNT_JSON."
        )

    if not bucket_name:
        bucket_name = f"{project_id}.appspot.com"

    if service_account_json:
        cred_dict = json.loads(service_account_json)
        cred = credentials.Certificate(cred_dict)
    else:
        cred = credentials.Certificate(service_account_path)
    firebase_admin.initialize_app(
        cred,
        {"projectId": project_id, "storageBucket": bucket_name},
    )
    _app_initialized = True


def get_firestore() -> firestore.Client:
    global _firestore_client
    if _firestore_client is not None:
        return _firestore_client

    _init_firebase_app()
    _firestore_client = firestore.client()
    return _firestore_client


def get_storage_bucket() -> storage.bucket:
    global _storage_bucket
    if _storage_bucket is not None:
        return _storage_bucket

    _init_firebase_app()
    _storage_bucket = storage.bucket()
    return _storage_bucket
