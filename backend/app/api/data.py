"""API routes for data management — upload, query, reset."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.data.store import odds_store

router = APIRouter(prefix="/api/data", tags=["data"])


class UploadRequest(BaseModel):
    """Accepts odds data in the same schema as sample_odds_data.json."""
    description: str = Field(default="User-uploaded odds data")
    generated: str = Field(default="")
    notes: list[str] = Field(default_factory=list)
    odds: list[dict] = Field(description="Array of odds records")


@router.post("/upload")
async def upload_data(request: UploadRequest):
    """Upload new odds data, replacing the current dataset."""
    if not request.odds:
        raise HTTPException(status_code=400, detail="No odds records provided")

    # Validate structure of records
    required_fields = {"game_id", "sportsbook", "markets"}
    for i, record in enumerate(request.odds):  # Validate all records
        missing = required_fields - set(record.keys())
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Record {i} missing required fields: {missing}",
            )

    odds_store.load_data(request.model_dump())
    return {
        "message": f"Loaded {len(request.odds)} odds records",
        "games": len(odds_store.get_games()),
        "sportsbooks": odds_store.get_sportsbooks(),
    }


@router.post("/reset")
async def reset_data():
    """Reset to sample data."""
    odds_store.reset()
    return {
        "message": "Reset to sample data",
        "records": len(odds_store.get_all_odds()),
    }


@router.post("/load-alt")
async def load_alt_data():
    """Load the alternative sample dataset (March 22 slate)."""
    odds_store.load_alt_sample()
    return {
        "message": f"Loaded alternative dataset",
        "games": len(odds_store.get_games()),
        "sportsbooks": odds_store.get_sportsbooks(),
    }


@router.get("/datasets")
async def list_datasets():
    """List available built-in datasets."""
    return {
        "datasets": [
            {"id": "sample", "name": "March 20 Slate", "games": 10, "sportsbooks": 8, "records": 80},
            {"id": "alt", "name": "March 22 Slate", "games": 5, "sportsbooks": 6, "records": 30},
        ]
    }


@router.get("/games")
async def list_games():
    """List all games in the current dataset."""
    return {
        "games": odds_store.get_games(),
        "count": len(odds_store.get_games()),
    }


@router.get("/games/{game_id}")
async def get_game_odds(game_id: str, sportsbook: str | None = None):
    """Get odds for a specific game, optionally filtered by sportsbook."""
    records = odds_store.get_odds_for_game(game_id, sportsbook=sportsbook)
    if not records:
        raise HTTPException(status_code=404, detail=f"No data for game {game_id}")
    return {"game_id": game_id, "records": records, "count": len(records)}


@router.get("/sportsbooks")
async def list_sportsbooks():
    """List all sportsbooks in the current dataset."""
    return {"sportsbooks": odds_store.get_sportsbooks()}


@router.get("/metadata")
async def get_metadata():
    """Get dataset metadata."""
    return odds_store.metadata
