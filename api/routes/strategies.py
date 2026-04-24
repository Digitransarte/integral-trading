from fastapi import APIRouter
router = APIRouter()

@router.get("/")
def list_strategies():
    return {"strategies": ["ep", "canslim"]}
