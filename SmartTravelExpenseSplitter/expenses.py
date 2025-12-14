"""
Expenses Module

This module handles all expense-related operations for the travel expense
splitter application.

Features:
    - Add/edit/delete expenses
    - Categorize expenses (food, hotel, transport, fun, misc)
    - Track who paid and who benefits
    - Support for partial beneficiary lists

Data Model:
    Expense stored at: trips/{trip_id}/expenses/{expense_id}
    Fields:
        - expense_id: string (E001, E002, ... format)
        - payer_id: string (participant_id who paid)
        - amount: float (must be > 0)
        - category: string (food, hotel, transport, fun, misc)
        - beneficiaries: list of participant_ids
        - date: string (YYYY-MM-DD)
        - note: string or None

Functions:
    add_expense: Add a new expense to a trip.
    get_expenses: Get all expenses for a trip.
"""

import re
from datetime import datetime
from typing import Optional
from config.firebase_config import get_db


# Valid expense categories
VALID_CATEGORIES = {"food", "hotel", "transport", "fun", "misc"}


class Expense:
    """
    Represents a single expense in the trip.
    
    Attributes:
        expense_id (str): Unique identifier in E### format.
        payer_id (str): Participant ID of who paid.
        amount (float): Amount of the expense (must be > 0).
        category (str): One of: food, hotel, transport, fun, misc.
        beneficiaries (list[str]): List of participant IDs who benefit.
        date (str): Date of expense (YYYY-MM-DD).
        note (str | None): Optional description/note.
    """
    
    def __init__(
        self,
        expense_id: str,
        payer_id: str,
        amount: float,
        category: str,
        beneficiaries: list[str],
        date: str,
        note: Optional[str] = None
    ):
        self.expense_id = expense_id
        self.payer_id = payer_id
        self.amount = amount
        self.category = category
        self.beneficiaries = beneficiaries
        self.date = date
        self.note = note
    
    def to_dict(self) -> dict:
        """Convert expense to dictionary for Firestore storage."""
        return {
            "expense_id": self.expense_id,
            "payer_id": self.payer_id,
            "amount": self.amount,
            "category": self.category,
            "beneficiaries": self.beneficiaries,
            "date": self.date,
            "note": self.note
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Expense":
        """Create an Expense instance from a dictionary."""
        return cls(
            expense_id=data.get("expense_id"),
            payer_id=data.get("payer_id"),
            amount=data.get("amount"),
            category=data.get("category"),
            beneficiaries=data.get("beneficiaries", []),
            date=data.get("date"),
            note=data.get("note")
        )
    
    def __repr__(self) -> str:
        """Return string representation of expense."""
        return f"Expense(id='{self.expense_id}', payer='{self.payer_id}', amount={self.amount}, category='{self.category}')"


def _generate_next_expense_id(trip_id: str) -> str:
    """
    Generate the next sequential expense ID for a trip.
    
    Format: E001, E002, E003, ...
    
    Logic:
        1. Fetch all existing expense document IDs for the trip
        2. Extract numeric suffix from IDs matching E### format (e.g., E001 -> 1)
        3. Find the highest existing number
        4. Generate next ID with zero-padded 3-digit suffix
        5. If no valid E### IDs exist, start from E001
    
    Args:
        trip_id: The ID of the trip.
    
    Returns:
        str: Next expense ID in format E### (e.g., E001, E002).
    """
    db = get_db()
    if db is None:
        raise RuntimeError("Firestore is not available")
    
    # Fetch all existing expense documents for this trip
    expenses_ref = db.collection("trips").document(trip_id).collection("expenses")
    docs = expenses_ref.stream()
    
    # Extract numeric suffixes from IDs that match E### format
    # Handles edge case where some IDs may not follow E### format (e.g., legacy data)
    max_num = 0
    pattern = re.compile(r'^E(\d+)$')
    
    for doc in docs:
        match = pattern.match(doc.id)
        if match:
            num = int(match.group(1))
            if num > max_num:
                max_num = num
    
    # Generate next ID with 3-digit zero padding
    next_num = max_num + 1
    return f"E{next_num:03d}"


def _validate_date(date_str: str, field_name: str) -> bool:
    """
    Validate date string format (YYYY-MM-DD).
    
    Args:
        date_str: Date string to validate.
        field_name: Name of the field for error messages.
    
    Returns:
        bool: True if valid.
    
    Raises:
        ValueError: If date format is invalid.
    """
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        raise ValueError(f"{field_name} must be in YYYY-MM-DD format, got: {date_str}")


def _validate_non_empty_string(value: str, field_name: str) -> bool:
    """
    Validate that a string is non-empty.
    
    Args:
        value: String to validate.
        field_name: Name of the field for error messages.
    
    Returns:
        bool: True if valid.
    
    Raises:
        ValueError: If string is empty or not a string.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return True


def _get_participant_ids(trip_id: str) -> set[str]:
    """
    Get all participant IDs for a trip.
    
    Args:
        trip_id: The ID of the trip.
    
    Returns:
        set[str]: Set of participant IDs.
    """
    db = get_db()
    if db is None:
        raise RuntimeError("Firestore is not available")
    
    docs = db.collection("trips").document(trip_id).collection("participants").stream()
    return {doc.id for doc in docs}


def add_expense(
    trip_id: str,
    payer_id: str,
    amount: float,
    category: str,
    beneficiaries: list[str],
    date: str,
    note: Optional[str] = None
) -> Expense:
    """
    Add a new expense to a trip.
    
    Args:
        trip_id: The ID of the trip.
        payer_id: Participant ID of who paid the expense.
        amount: Amount of the expense (must be > 0).
        category: Category of expense (food, hotel, transport, fun, misc).
        beneficiaries: List of participant IDs who benefit from this expense.
        date: Date of the expense (YYYY-MM-DD).
        note: Optional description or note for the expense.
    
    Returns:
        Expense: The created expense object.
    
    Raises:
        ValueError: If input validation fails.
        RuntimeError: If Firestore is not available.
    
    Notes:
        - Payer does NOT have to be in beneficiaries list
        - Beneficiaries can be a subset of trip participants
        - No cost splitting is performed here
    """
    # Validate inputs
    _validate_non_empty_string(trip_id, "trip_id")
    _validate_non_empty_string(payer_id, "payer_id")
    _validate_date(date, "date")
    
    # Validate amount is positive
    if not isinstance(amount, (int, float)) or amount <= 0:
        raise ValueError(f"amount must be a positive number, got: {amount}")
    
    # Validate category
    if category not in VALID_CATEGORIES:
        raise ValueError(f"category must be one of {VALID_CATEGORIES}, got: {category}")
    
    # Validate beneficiaries is a non-empty list
    if not isinstance(beneficiaries, list) or len(beneficiaries) == 0:
        raise ValueError("beneficiaries must be a non-empty list of participant IDs")
    
    db = get_db()
    if db is None:
        raise RuntimeError("Firestore is not available")
    
    # Get existing participant IDs to validate payer and beneficiaries
    existing_participants = _get_participant_ids(trip_id)
    
    # Validate payer_id exists
    if payer_id not in existing_participants:
        raise ValueError(f"payer_id '{payer_id}' does not exist in trip {trip_id}")
    
    # Validate all beneficiaries exist
    for beneficiary in beneficiaries:
        if beneficiary not in existing_participants:
            raise ValueError(f"beneficiary '{beneficiary}' does not exist in trip {trip_id}")
    
    # Generate sequential expense ID (E001, E002, ...)
    expense_id = _generate_next_expense_id(trip_id)
    
    # Create expense with the generated ID
    expense = Expense(
        expense_id=expense_id,
        payer_id=payer_id,
        amount=float(amount),  # Ensure float type
        category=category,
        beneficiaries=beneficiaries,
        date=date,
        note=note.strip() if note else None
    )
    
    # Store in Firestore at trips/{trip_id}/expenses/{expense_id}
    doc_ref = db.collection("trips").document(trip_id) \
                .collection("expenses").document(expense.expense_id)
    doc_ref.set(expense.to_dict())
    
    return expense


def get_expenses(trip_id: str) -> list[Expense]:
    """
    Get all expenses for a trip.
    
    Args:
        trip_id: The ID of the trip.
    
    Returns:
        list[Expense]: List of all expenses for the trip.
    
    Raises:
        ValueError: If trip_id is invalid.
        RuntimeError: If Firestore is not available.
    """
    _validate_non_empty_string(trip_id, "trip_id")
    
    db = get_db()
    if db is None:
        raise RuntimeError("Firestore is not available")
    
    # Query all expenses for the trip
    docs = db.collection("trips").document(trip_id) \
             .collection("expenses").stream()
    
    return [Expense.from_dict(doc.to_dict()) for doc in docs]
