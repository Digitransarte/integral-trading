from fastapi import APIRouter
router = APIRouter()

@router.get("/candidates")
def get_candidates():
    return {"candidates": []}
