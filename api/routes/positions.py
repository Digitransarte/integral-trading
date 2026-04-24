from fastapi import APIRouter
router = APIRouter()

@router.get("/")
def list_positions():
    from engine.database import get_open_positions
    return {"open": get_open_positions(), "closed": []}
