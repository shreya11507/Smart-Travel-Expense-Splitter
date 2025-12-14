"""
SmartTravelExpenseSplitter - FastAPI Web Backend

This module serves as the main entry point for the web-based travel expense
splitting application using FastAPI.

Features:
    - RESTful API for managing trips, participants, and expenses
    - Integration with Firebase Firestore backend
    - Expense splitting and settlement calculations
    - Analytics and transparency reports

Endpoints:
    POST /trips                         - Create a new trip
    POST /trips/{trip_id}/participants  - Add participant to trip
    POST /trips/{trip_id}/expenses      - Add expense to trip
    GET  /trips/{trip_id}/calculate     - Calculate and persist results
    GET  /trips/{trip_id}/summary       - Get stored results

Usage:
    uvicorn main:app --reload
"""

import uuid
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# Import existing business logic modules
from participants import add_participant, get_participants, Participant
from expenses import add_expense, get_expenses, Expense, VALID_CATEGORIES
from splitter import calculate_balances
from settlement import optimize_settlements
from analytics import generate_analytics
from utils import explain_all_participants
from firebase_store import (
    save_balances,
    save_settlements,
    save_analytics,
    save_explanations
)
from config.firebase_config import get_db


# =============================================================================
# Pydantic Models for Request/Response Validation
# =============================================================================

class TripCreate(BaseModel):
    """Request model for creating a new trip."""
    name: Optional[str] = Field(None, description="Optional trip name")


class TripResponse(BaseModel):
    """Response model for trip creation."""
    trip_id: str
    message: str


class ParticipantCreate(BaseModel):
    """Request model for adding a participant."""
    name: str = Field(..., min_length=1, description="Participant name")
    start_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Start date (YYYY-MM-DD)")
    group_id: Optional[str] = Field(None, description="Optional group identifier")


class ParticipantResponse(BaseModel):
    """Response model for participant data."""
    participant_id: str
    name: str
    start_date: str
    end_date: Optional[str]
    group_id: Optional[str]


class ExpenseCreate(BaseModel):
    """Request model for adding an expense."""
    payer_id: str = Field(..., min_length=1, description="Participant ID of payer")
    amount: float = Field(..., gt=0, description="Expense amount (must be > 0)")
    category: str = Field(..., description="Expense category")
    beneficiaries: list[str] = Field(..., min_length=1, description="List of beneficiary participant IDs")
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Expense date (YYYY-MM-DD)")
    note: Optional[str] = Field(None, description="Optional note")


class ExpenseResponse(BaseModel):
    """Response model for expense data."""
    expense_id: str
    payer_id: str
    amount: float
    category: str
    beneficiaries: list[str]
    date: str
    note: Optional[str]


class CalculateResponse(BaseModel):
    """Response model for calculation results."""
    balances: dict
    settlements: list
    analytics: dict
    warnings: list
    explanations: list


class SummaryResponse(BaseModel):
    """Response model for stored summary."""
    balances: dict
    settlements: list
    analytics: dict
    explanations: list


# =============================================================================
# FastAPI Application
# =============================================================================

app = FastAPI(
    title="Smart Travel Expense Splitter",
    description="A fair and transparent expense splitting API for group travel",
    version="1.0.0"
)


# =============================================================================
# Helper Functions
# =============================================================================

def _generate_trip_id() -> str:
    """
    Generate a unique trip ID.
    
    Format: trip_{short_uuid}
    """
    return f"trip_{uuid.uuid4().hex[:8]}"


def _participant_to_dict(p: Participant) -> dict:
    """Convert Participant object to dictionary."""
    return {
        "participant_id": p.participant_id,
        "name": p.name,
        "start_date": p.start_date,
        "end_date": p.end_date,
        "group_id": p.group_id
    }


def _expense_to_dict(e: Expense) -> dict:
    """Convert Expense object to dictionary."""
    return {
        "expense_id": e.expense_id,
        "payer_id": e.payer_id,
        "amount": e.amount,
        "category": e.category,
        "beneficiaries": e.beneficiaries,
        "date": e.date,
        "note": e.note
    }


# =============================================================================
# API Endpoints
# =============================================================================

@app.post("/trips", response_model=TripResponse, status_code=201)
async def create_trip(trip_data: TripCreate = None):
    """
    Create a new trip.
    
    Request flow:
        1. Generate unique trip_id
        2. Create trip document in Firestore
        3. Return trip_id to client
    """
    try:
        db = get_db()
        if db is None:
            raise HTTPException(status_code=503, detail="Database not available")
        
        # Generate unique trip ID
        trip_id = _generate_trip_id()
        
        # Create trip document in Firestore
        trip_doc = {
            "trip_id": trip_id,
            "name": trip_data.name if trip_data and trip_data.name else trip_id,
            "created_at": str(uuid.uuid1())  # Timestamp placeholder
        }
        db.collection("trips").document(trip_id).set(trip_doc)
        
        return TripResponse(
            trip_id=trip_id,
            message="Trip created successfully"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/trips/{trip_id}/participants", response_model=ParticipantResponse, status_code=201)
async def add_trip_participant(trip_id: str, participant_data: ParticipantCreate):
    """
    Add a participant to a trip.
    
    Request flow:
        1. Validate input using Pydantic model
        2. Call add_participant() from participants.py
        3. Return created participant data
    """
    try:
        # Reuse existing add_participant logic
        participant = add_participant(
            trip_id=trip_id,
            name=participant_data.name,
            start_date=participant_data.start_date,
            group_id=participant_data.group_id
        )
        
        return ParticipantResponse(
            participant_id=participant.participant_id,
            name=participant.name,
            start_date=participant.start_date,
            end_date=participant.end_date,
            group_id=participant.group_id
        )
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/trips/{trip_id}/expenses", response_model=ExpenseResponse, status_code=201)
async def add_trip_expense(trip_id: str, expense_data: ExpenseCreate):
    """
    Add an expense to a trip.
    
    Request flow:
        1. Validate input using Pydantic model
        2. Validate category is valid
        3. Call add_expense() from expenses.py
        4. Return created expense data
    """
    try:
        # Validate category
        if expense_data.category not in VALID_CATEGORIES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid category. Must be one of: {VALID_CATEGORIES}"
            )
        
        # Reuse existing add_expense logic
        expense = add_expense(
            trip_id=trip_id,
            payer_id=expense_data.payer_id,
            amount=expense_data.amount,
            category=expense_data.category,
            beneficiaries=expense_data.beneficiaries,
            date=expense_data.date,
            note=expense_data.note
        )
        
        return ExpenseResponse(
            expense_id=expense.expense_id,
            payer_id=expense.payer_id,
            amount=expense.amount,
            category=expense.category,
            beneficiaries=expense.beneficiaries,
            date=expense.date,
            note=expense.note
        )
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/trips/{trip_id}/calculate", response_model=CalculateResponse)
async def calculate_trip_results(trip_id: str):
    """
    Calculate and persist all results for a trip.
    
    Request flow:
        1. Fetch participants from Firestore
        2. Fetch expenses from Firestore
        3. Calculate balances (splitter.py)
        4. Optimize settlements (settlement.py)
        5. Generate analytics (analytics.py)
        6. Generate explanations (utils.py)
        7. Persist all results to Firestore (firebase_store.py)
        8. Return complete results
    """
    try:
        # Step 1: Fetch participants from Firestore
        participants_list = get_participants(trip_id)
        if not participants_list:
            raise HTTPException(status_code=404, detail="No participants found for this trip")
        
        # Convert to dict format for calculation functions
        participants_dicts = [_participant_to_dict(p) for p in participants_list]
        
        # Step 2: Fetch expenses from Firestore
        expenses_list = get_expenses(trip_id)
        expenses_dicts = [_expense_to_dict(e) for e in expenses_list]
        
        # Step 3: Calculate balances using splitter.py
        balances = calculate_balances(participants_dicts, expenses_dicts)
        
        # Step 4: Optimize settlements using settlement.py
        settlements = optimize_settlements(balances)
        
        # Step 5: Generate analytics using analytics.py
        analytics_result = generate_analytics(participants_dicts, expenses_dicts)
        analytics = analytics_result["analytics"]
        warnings = analytics_result["warnings"]
        
        # Step 6: Generate explanations using utils.py
        explanations = explain_all_participants(participants_dicts, expenses_dicts, balances)
        
        # Step 7: Persist all results to Firestore using firebase_store.py
        save_balances(trip_id, balances)
        save_settlements(trip_id, settlements)
        save_analytics(trip_id, analytics)
        save_explanations(trip_id, explanations)
        
        # Step 8: Return complete results
        return CalculateResponse(
            balances=balances,
            settlements=settlements,
            analytics=analytics,
            warnings=warnings,
            explanations=explanations
        )
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/trips/{trip_id}/summary", response_model=SummaryResponse)
async def get_trip_summary(trip_id: str):
    """
    Get stored results from Firestore.
    
    Request flow:
        1. Fetch balances from Firestore
        2. Fetch settlements from Firestore
        3. Fetch analytics from Firestore
        4. Fetch explanations from Firestore
        5. Return combined summary
    """
    try:
        db = get_db()
        if db is None:
            raise HTTPException(status_code=503, detail="Database not available")
        
        # Fetch balances
        balances = {}
        balances_ref = db.collection("trips").document(trip_id) \
                        .collection("results").document("balances") \
                        .collection("balances").stream()
        for doc in balances_ref:
            data = doc.to_dict()
            balances[doc.id] = {
                "total_paid": data.get("total_paid", 0),
                "total_share": data.get("total_share", 0),
                "net_balance": data.get("net_balance", 0)
            }
        
        # Fetch settlements
        settlements = []
        settlements_ref = db.collection("trips").document(trip_id) \
                           .collection("results").document("settlements") \
                           .collection("settlements").stream()
        for doc in settlements_ref:
            data = doc.to_dict()
            settlements.append({
                "settlement_id": data.get("settlement_id"),
                "from_participant": data.get("from_participant"),
                "to_participant": data.get("to_participant"),
                "amount": data.get("amount")
            })
        
        # Fetch analytics
        analytics = {}
        analytics_ref = db.collection("trips").document(trip_id) \
                         .collection("results").document("analytics") \
                         .collection("analytics").document("summary").get()
        if analytics_ref.exists:
            data = analytics_ref.to_dict()
            analytics = {
                "category_breakdown": data.get("category_breakdown", {}),
                "daily_spending": data.get("daily_spending", {}),
                "highest_spending_day": data.get("highest_spending_day", {}),
                "payer_totals": data.get("payer_totals", {})
            }
        
        # Fetch explanations
        explanations = []
        explanations_ref = db.collection("trips").document(trip_id) \
                            .collection("results").document("explanations") \
                            .collection("explanations").stream()
        for doc in explanations_ref:
            explanations.append(doc.to_dict())
        
        # Check if any results exist
        if not balances and not settlements and not analytics:
            raise HTTPException(
                status_code=404,
                detail="No results found. Call /trips/{trip_id}/calculate first."
            )
        
        return SummaryResponse(
            balances=balances,
            settlements=settlements,
            analytics=analytics,
            explanations=explanations
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Health Check Endpoint
# =============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint to verify API is running."""
    return {"status": "healthy", "service": "Smart Travel Expense Splitter"}


# =============================================================================
# Run with: python main.py
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
