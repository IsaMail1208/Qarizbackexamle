from datetime import date, datetime, timezone
from io import BytesIO
import os

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
from pydantic import ValidationError

from firebase import get_firestore, get_storage_bucket
from models import CaseCreate, CaseListResponse, CaseRecord

load_dotenv()

app = FastAPI(title="Qariz API")

_extra_origins = [
    "https://qarizfrontexamle-6jltcpox7-ismail-s-projects23.vercel.app",
]

_frontend_origins = os.getenv("FRONTEND_ORIGIN", "*")
if not _frontend_origins or _frontend_origins == "*":
    _origins = ["*"]
else:
    _origins = [o.strip() for o in _frontend_origins.split(",") if o.strip()]
    for origin in _extra_origins:
        if origin not in _origins:
            _origins.append(origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Fallback: ensure CORS header is present on all responses (helps when some errors bypass middleware)
@app.middleware("http")
async def add_cors_header(request, call_next):
    response = await call_next(request)
    if "access-control-allow-origin" not in {k.lower() for k in response.headers.keys()}:
        # mirror single allowed origin or set wildcard
        response.headers["Access-Control-Allow-Origin"] = _origins[0] if _origins else "*"
    return response


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/cases", response_model=CaseListResponse)
async def list_cases(
    q: str | None = None,
    limit: int = 12,
    cursor: str | None = None,
) -> CaseListResponse:
    try:
        db = get_firestore()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if limit < 1 or limit > 50:
        raise HTTPException(status_code=400, detail="Invalid limit")

    collection = db.collection("cases")
    if q:
        term = q.strip().lower()
        name_query = (
            collection.order_by("full_name_lower")
            .start_at([term])
            .end_at([f"{term}\uf8ff"])
            .limit(limit)
        )
        passport_query = (
            collection.order_by("passport_data_lower")
            .start_at([term])
            .end_at([f"{term}\uf8ff"])
            .limit(limit)
        )
        docs = list(name_query.stream()) + list(passport_query.stream())
        unique_docs: dict[str, dict] = {}
        for doc in docs:
            data = doc.to_dict()
            data["id"] = doc.id
            unique_docs[doc.id] = data

        results: list[CaseRecord] = []
        for data in sorted(
            unique_docs.values(),
            key=lambda item: item.get("submitted_at"),
            reverse=True,
        )[:limit]:
            results.append(CaseRecord(**data))

        return CaseListResponse(items=results, next_cursor=None)

    query = collection.order_by("submitted_at", direction="DESCENDING")

    if cursor:
        snapshot = collection.document(cursor).get()
        if not snapshot.exists:
            raise HTTPException(status_code=400, detail="Invalid cursor")
        query = query.start_after(snapshot)

    docs = list(query.limit(limit + 1).stream())
    has_more = len(docs) > limit
    docs = docs[:limit]

    results: list[CaseRecord] = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        results.append(CaseRecord(**data))

    next_cursor = docs[-1].id if has_more and docs else None
    return CaseListResponse(items=results, next_cursor=next_cursor)


def _parse_birth_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid birth date") from exc


def _parse_damage_amount(value: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid damage amount") from exc


def _compress_image(upload: UploadFile) -> tuple[BytesIO, str]:
    try:
        source = Image.open(upload.file)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid image file") from exc

    if source.mode not in ("RGB", "L"):
        source = source.convert("RGB")

    max_size = 1600
    source.thumbnail((max_size, max_size))

    output = BytesIO()
    source.save(output, format="JPEG", quality=80, optimize=True)
    output.seek(0)
    return output, "image/jpeg"


@app.post("/cases", response_model=CaseRecord)
async def create_case(
    full_name: str = Form(...),
    birth_date: str = Form(...),
    passport_data: str = Form(...),
    damage_amount: str = Form(...),
    submitted_by: str = Form(...),
    description: str = Form(...),
    photo: UploadFile | None = File(default=None),
) -> CaseRecord:
    try:
        db = get_firestore()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    try:
        payload = CaseCreate(
            full_name=full_name,
            birth_date=_parse_birth_date(birth_date),
            passport_data=passport_data,
            damage_amount=_parse_damage_amount(damage_amount),
            submitted_by=submitted_by,
            description=description,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.errors()) from exc

    submitted_at = datetime.now(timezone.utc)
    doc_ref = db.collection("cases").document()
    data = payload.model_dump()
    data["submitted_at"] = submitted_at
    data["birth_date"] = payload.birth_date.isoformat()
    data["full_name_lower"] = payload.full_name.lower()
    data["passport_data_lower"] = payload.passport_data.lower()

    photo_blob = None
    if photo and photo.filename:
        if photo.content_type and not photo.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="Invalid photo type")
        try:
            bucket = get_storage_bucket()
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        image_stream, content_type = _compress_image(photo)
        photo_blob = bucket.blob(f"cases/{doc_ref.id}/photo.jpg")
        photo_blob.upload_from_file(image_stream, content_type=content_type)
        photo_blob.make_public()
        data["photo_url"] = photo_blob.public_url

    try:
        record = CaseRecord(id=doc_ref.id, **data)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        doc_ref.set(data)
    except Exception as exc:
        if photo_blob is not None:
            try:
                photo_blob.delete()
            except Exception:
                pass
        raise exc
    return record
