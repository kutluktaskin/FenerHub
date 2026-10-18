import json
import os

from fastapi import APIRouter, HTTPException

router = APIRouter()

# standings_cache.json, backend/ klasöründe (sync.py ile aynı yerde)
CACHE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "standings_cache.json")


@router.get("/standings/{competition}")
def get_standings(competition: str):
    if competition not in ("super_lig", "uefa"):
        raise HTTPException(status_code=404, detail="Bilinmeyen lig")
    try:
        with open(CACHE, encoding="utf-8") as f:
            tables = json.load(f).get("tables", {})
    except FileNotFoundError:
        return []
    return [
        {
            **r,
            "goal_difference": r["goal_diff"],
            "is_fenerbahce": r["team"] == "Fenerbahçe",
        }
        for r in tables.get(competition, [])
    ]