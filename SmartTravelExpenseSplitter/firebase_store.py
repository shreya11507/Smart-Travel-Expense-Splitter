"""
Firebase Store Module

This module handles saving computed results to Firebase Firestore for the
travel expense splitter application.

Features:
    - Save balances per participant
    - Save settlement transactions
    - Save analytics summary
    - Save explanations per participant
    - All saves are idempotent (safe to overwrite)

Firestore Structure:
    trips/{trip_id}/results/balances/{participant_id}
        - participant_id: string
        - total_paid: float
        - total_share: float
        - net_balance: float
        - updated_at: timestamp
    
    trips/{trip_id}/results/settlements/{settlement_id}
        - settlement_id: string (S001, S002, ...)
        - from_participant: string
        - to_participant: string
        - amount: float
        - updated_at: timestamp
    
    trips/{trip_id}/results/analytics/summary
        - category_breakdown: dict
        - daily_spending: dict
        - highest_spending_day: dict
        - payer_totals: dict
        - updated_at: timestamp
    
    trips/{trip_id}/results/explanations/{participant_id}
        - participant_id: string
        - expense_contributions: list
        - total_share: float
        - total_paid: float
        - net_balance: float
        - updated_at: timestamp

Functions:
    save_balances: Save participant balances to Firestore.
    save_settlements: Save settlement transactions to Firestore.
    save_analytics: Save analytics summary to Firestore.
    save_explanations: Save explanations to Firestore.
"""

from datetime import datetime, timezone
from config.firebase_config import get_db


def _get_timestamp() -> str:
    """
    Get current UTC timestamp in ISO format.
    
    Returns:
        str: ISO formatted timestamp.
    """
    return datetime.now(timezone.utc).isoformat()


def _validate_trip_id(trip_id: str) -> None:
    """
    Validate that trip_id is a non-empty string.
    
    Args:
        trip_id: The trip ID to validate.
    
    Raises:
        ValueError: If trip_id is invalid.
    """
    if not isinstance(trip_id, str) or not trip_id.strip():
        raise ValueError("trip_id must be a non-empty string")


def save_balances(trip_id: str, balances: dict) -> dict:
    """
    Save participant balances to Firestore.
    
    Stores each participant's balance as a separate document at:
        trips/{trip_id}/results/balances/{participant_id}
    
    Args:
        trip_id: The ID of the trip.
        balances: Dict keyed by participant_id containing:
            - total_paid: float
            - total_share: float
            - net_balance: float
    
    Returns:
        dict: Summary of saved documents with count and participant IDs.
    
    Raises:
        ValueError: If trip_id is invalid.
        RuntimeError: If Firestore is not available.
    
    Notes:
        - Overwrites existing balance documents (idempotent)
        - Adds updated_at timestamp to each document
    """
    _validate_trip_id(trip_id)
    
    db = get_db()
    if db is None:
        raise RuntimeError("Firestore is not available")
    
    timestamp = _get_timestamp()
    saved_ids = []
    
    # Save each participant's balance as a separate document
    for participant_id, balance_data in balances.items():
        doc_data = {
            "participant_id": participant_id,
            "total_paid": balance_data.get("total_paid", 0.0),
            "total_share": balance_data.get("total_share", 0.0),
            "net_balance": balance_data.get("net_balance", 0.0),
            "updated_at": timestamp
        }
        
        # Store at trips/{trip_id}/results/balances/{participant_id}
        doc_ref = db.collection("trips").document(trip_id) \
                    .collection("results").document("balances") \
                    .collection("balances").document(participant_id)
        doc_ref.set(doc_data)
        saved_ids.append(participant_id)
    
    return {
        "saved_count": len(saved_ids),
        "participant_ids": saved_ids,
        "updated_at": timestamp
    }


def save_settlements(trip_id: str, settlements: list) -> dict:
    """
    Save settlement transactions to Firestore.
    
    Generates sequential settlement IDs (S001, S002, ...) and stores at:
        trips/{trip_id}/results/settlements/{settlement_id}
    
    Args:
        trip_id: The ID of the trip.
        settlements: List of settlement dicts containing:
            - from_participant: string (debtor)
            - to_participant: string (creditor)
            - amount: float
    
    Returns:
        dict: Summary of saved documents with count and settlement IDs.
    
    Raises:
        ValueError: If trip_id is invalid.
        RuntimeError: If Firestore is not available.
    
    Notes:
        - Overwrites existing settlement documents (idempotent)
        - Generates new sequential IDs (S001, S002, ...)
        - Adds updated_at timestamp to each document
    """
    _validate_trip_id(trip_id)
    
    db = get_db()
    if db is None:
        raise RuntimeError("Firestore is not available")
    
    timestamp = _get_timestamp()
    saved_ids = []
    
    # Generate sequential settlement IDs and save each transaction
    for index, settlement in enumerate(settlements, start=1):
        # Generate settlement ID with 3-digit zero padding (S001, S002, ...)
        settlement_id = f"S{index:03d}"
        
        doc_data = {
            "settlement_id": settlement_id,
            "from_participant": settlement.get("from_participant"),
            "to_participant": settlement.get("to_participant"),
            "amount": settlement.get("amount", 0.0),
            "updated_at": timestamp
        }
        
        # Store at trips/{trip_id}/results/settlements/{settlement_id}
        doc_ref = db.collection("trips").document(trip_id) \
                    .collection("results").document("settlements") \
                    .collection("settlements").document(settlement_id)
        doc_ref.set(doc_data)
        saved_ids.append(settlement_id)
    
    return {
        "saved_count": len(saved_ids),
        "settlement_ids": saved_ids,
        "updated_at": timestamp
    }


def save_analytics(trip_id: str, analytics: dict) -> dict:
    """
    Save analytics summary to Firestore.
    
    Stores the full analytics output as a single document at:
        trips/{trip_id}/results/analytics/summary
    
    Args:
        trip_id: The ID of the trip.
        analytics: Dict containing:
            - category_breakdown: dict
            - daily_spending: dict
            - highest_spending_day: dict
            - payer_totals: dict
    
    Returns:
        dict: Confirmation with document path and timestamp.
    
    Raises:
        ValueError: If trip_id is invalid.
        RuntimeError: If Firestore is not available.
    
    Notes:
        - Overwrites existing analytics document (idempotent)
        - Adds updated_at timestamp
    """
    _validate_trip_id(trip_id)
    
    db = get_db()
    if db is None:
        raise RuntimeError("Firestore is not available")
    
    timestamp = _get_timestamp()
    
    # Build document with all analytics data
    doc_data = {
        "category_breakdown": analytics.get("category_breakdown", {}),
        "daily_spending": analytics.get("daily_spending", {}),
        "highest_spending_day": analytics.get("highest_spending_day", {}),
        "payer_totals": analytics.get("payer_totals", {}),
        "updated_at": timestamp
    }
    
    # Store at trips/{trip_id}/results/analytics/summary
    doc_ref = db.collection("trips").document(trip_id) \
                .collection("results").document("analytics") \
                .collection("analytics").document("summary")
    doc_ref.set(doc_data)
    
    return {
        "saved": True,
        "path": f"trips/{trip_id}/results/analytics/summary",
        "updated_at": timestamp
    }


def save_explanations(trip_id: str, explanations) -> dict:
    """
    Save participant explanations to Firestore.
    
    Stores each participant's explanation as a separate document at:
        trips/{trip_id}/results/explanations/{participant_id}
    
    Args:
        trip_id: The ID of the trip.
        explanations: Either:
            - List of explanation dicts with participant_id field, OR
            - Dict keyed by participant_id with explanation data
            Each explanation contains:
                - participant_id: string (in list format) or key (in dict format)
                - expense_contributions: list (optional)
                - total_share: float (optional)
                - total_paid: float (optional)
                - net_balance: float (optional)
    
    Returns:
        dict: Summary of saved documents with count and participant IDs.
    
    Raises:
        ValueError: If trip_id is invalid.
        RuntimeError: If Firestore is not available.
    
    Notes:
        - Overwrites existing explanation documents (idempotent)
        - Adds updated_at timestamp to each document
        - Accepts both list and dict formats for flexibility
    """
    _validate_trip_id(trip_id)
    
    db = get_db()
    if db is None:
        raise RuntimeError("Firestore is not available")
    
    timestamp = _get_timestamp()
    saved_ids = []
    
    # Handle both dict and list formats for explanations
    if isinstance(explanations, dict):
        # Dict format: {participant_id: explanation_data}
        items = [
            (pid, data) for pid, data in explanations.items()
        ]
    else:
        # List format: [{participant_id: ..., ...}, ...]
        items = [
            (exp.get("participant_id"), exp) for exp in explanations
            if exp.get("participant_id")
        ]
    
    # Save each participant's explanation as a separate document
    for participant_id, explanation_data in items:
        if not participant_id:
            continue
        
        doc_data = {
            "participant_id": participant_id,
            "expense_contributions": explanation_data.get("expense_contributions", []),
            "total_share": explanation_data.get("total_share", 0.0),
            "total_paid": explanation_data.get("total_paid", 0.0),
            "net_balance": explanation_data.get("net_balance", 0.0),
            "updated_at": timestamp
        }
        
        # Store at trips/{trip_id}/results/explanations/{participant_id}
        doc_ref = db.collection("trips").document(trip_id) \
                    .collection("results").document("explanations") \
                    .collection("explanations").document(participant_id)
        doc_ref.set(doc_data)
        saved_ids.append(participant_id)
    
    return {
        "saved_count": len(saved_ids),
        "participant_ids": saved_ids,
        "updated_at": timestamp
    }
