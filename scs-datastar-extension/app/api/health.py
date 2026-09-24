from fastapi import APIRouter

router = APIRouter()

@router.get("/healthz")
async def healthz():
    return {"ok": True, "service": "scs-datastar-extension", "version": "0.1.0", "transport": "datastar-sse"}

@router.get("/readyz")
async def readyz():
    return {"ok": True}