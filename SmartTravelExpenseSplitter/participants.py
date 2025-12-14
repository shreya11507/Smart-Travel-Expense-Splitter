"""
Participants Module

This module handles all participant-related operations for the travel expense
splitter application.

Features:
    - Add/remove participants to a trip
    - Update participant information
    - Retrieve participant details
    - Manage participant groups
    - Support for mid-trip joins/leaves

Data Model:
    Participant stored at: trips/{trip_id}/participants/{participant_id}
    Fields:
        - participant_id: string (auto-generated if not provided)
        - name: string
        - start_date: string (YYYY-MM-DD)
        - end_date: string (YYYY-MM-DD) or None
        - group_id: string or None

Functions:
    add_participant: Add a new participant to a trip.
    remove_participant: Set end_date for a participant (soft delete).
    get_participants: Get all participants for a trip.
    get_active_participants: Get participants active on a specific date.
"""

import re
from datetime import datetime
from typing import Optional
from config.firebase_config import get_db


def _generate_next_participant_id(trip_id: str) -> str:
    """
    Generate the next sequential participant ID for a trip.
    
    Format: P001, P002, P003, ...
    
    Logic:
        1. Fetch all existing participant document IDs for the trip
        2. Extract numeric suffix from IDs matching P### format (e.g., P001 -> 1)
        3. Find the highest existing number
        4. Generate next ID with zero-padded 3-digit suffix
        5. If no valid P### IDs exist, start from P001
    
    Args:
        trip_id: The ID of the trip.
    
    Returns:
        str: Next participant ID in format P### (e.g., P001, P002).
    """
    db = get_db()
    if db is None:
        raise RuntimeError("Firestore is not available")
    
    # Fetch all existing participant documents for this trip
    participants_ref = db.collection("trips").document(trip_id).collection("participants")
    docs = participants_ref.stream()
    
    # Extract numeric suffixes from IDs that match P### format
    # Handles edge case where some IDs may not follow P### format (e.g., legacy UUIDs)
    max_num = 0
    pattern = re.compile(r'^P(\d+)$')
    
    for doc in docs:
        match = pattern.match(doc.id)
        if match:
            num = int(match.group(1))
            if num > max_num:
                max_num = num
    
    # Generate next ID with 3-digit zero padding
    next_num = max_num + 1
    return f"P{next_num:03d}"


class Participant:
    """
    Represents a participant in a trip.
    
    Attributes:
        participant_id (str): Unique identifier for the participant.
        name (str): Name of the participant.
        start_date (str): Date participant joined (YYYY-MM-DD).
        end_date (str | None): Date participant left (YYYY-MM-DD) or None if active.
        group_id (str | None): Optional group identifier.
    """
    
    def __init__(
        self,
        name: str,
        start_date: str,
        participant_id: Optional[str] = None,
        end_date: Optional[str] = None,
        group_id: Optional[str] = None
    ):
        self.participant_id = participant_id  # ID is generated externally via _generate_next_participant_id
        self.name = name
        self.start_date = start_date
        self.end_date = end_date
        self.group_id = group_id
    
    def to_dict(self) -> dict:
        """Convert participant to dictionary for Firestore storage."""
        return {
            "participant_id": self.participant_id,
            "name": self.name,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "group_id": self.group_id
        }
    
    def __repr__(self) -> str:
        """Return string representation of participant."""
        return f"Participant(name='{self.name}', start='{self.start_date}', end={self.end_date})"
    
    @classmethod
    def from_dict(cls, data: dict) -> "Participant":
        """Create a Participant instance from a dictionary."""
        return cls(
            participant_id=data.get("participant_id"),
            name=data.get("name"),
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            group_id=data.get("group_id")
        )


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


def add_participant(
    trip_id: str,
    name: str,
    start_date: str,
    group_id: Optional[str] = None
) -> Participant:
    """
    Add a new participant to a trip.
    
    Args:
        trip_id: The ID of the trip.
        name: Name of the participant.
        start_date: Date participant joins (YYYY-MM-DD).
        group_id: Optional group identifier.
    
    Returns:
        Participant: The created participant object.
    
    Raises:
        ValueError: If input validation fails.
        RuntimeError: If Firestore is not available.
    """
    # Validate inputs
    _validate_non_empty_string(trip_id, "trip_id")
    _validate_non_empty_string(name, "name")
    _validate_date(start_date, "start_date")
    
    db = get_db()
    if db is None:
        raise RuntimeError("Firestore is not available")
    
    # Generate sequential participant ID (P001, P002, ...)
    participant_id = _generate_next_participant_id(trip_id)
    
    # Create participant with the generated ID
    participant = Participant(
        name=name.strip(),
        start_date=start_date,
        participant_id=participant_id,
        group_id=group_id.strip() if group_id else None
    )
    
    # Store in Firestore
    doc_ref = db.collection("trips").document(trip_id) \
                .collection("participants").document(participant.participant_id)
    doc_ref.set(participant.to_dict())
    
    return participant


def remove_participant(
    trip_id: str,
    participant_id: str,
    end_date: str
) -> Participant:
    """
    Remove a participant from a trip by setting their end_date.
    
    Note: This performs a soft delete - the document is NOT deleted,
    only the end_date field is set.
    
    Args:
        trip_id: The ID of the trip.
        participant_id: The ID of the participant to remove.
        end_date: Date participant leaves (YYYY-MM-DD).
    
    Returns:
        Participant: The updated participant object.
    
    Raises:
        ValueError: If input validation fails or participant not found.
        RuntimeError: If Firestore is not available.
    """
    # Validate inputs
    _validate_non_empty_string(trip_id, "trip_id")
    _validate_non_empty_string(participant_id, "participant_id")
    _validate_date(end_date, "end_date")
    
    db = get_db()
    if db is None:
        raise RuntimeError("Firestore is not available")
    
    # Get participant document
    doc_ref = db.collection("trips").document(trip_id) \
                .collection("participants").document(participant_id)
    doc = doc_ref.get()
    
    if not doc.exists:
        raise ValueError(f"Participant {participant_id} not found in trip {trip_id}")
    
    # Validate end_date is not before start_date
    participant_data = doc.to_dict()
    start_date = participant_data.get("start_date")
    if start_date and end_date < start_date:
        raise ValueError(f"end_date ({end_date}) cannot be before start_date ({start_date})")
    
    # Update end_date
    doc_ref.update({"end_date": end_date})
    
    # Return updated participant
    participant_data["end_date"] = end_date
    return Participant.from_dict(participant_data)


def get_participants(trip_id: str) -> list[Participant]:
    """
    Get all participants for a trip.
    
    Args:
        trip_id: The ID of the trip.
    
    Returns:
        list[Participant]: List of all participants (active and inactive).
    
    Raises:
        ValueError: If trip_id is invalid.
        RuntimeError: If Firestore is not available.
    """
    _validate_non_empty_string(trip_id, "trip_id")
    
    db = get_db()
    if db is None:
        raise RuntimeError("Firestore is not available")
    
    # Query all participants
    docs = db.collection("trips").document(trip_id) \
             .collection("participants").stream()
    
    return [Participant.from_dict(doc.to_dict()) for doc in docs]


def get_active_participants(trip_id: str, on_date: str) -> list[Participant]:
    """
    Get participants active on a specific date.
    
    A participant is active on a date if:
        - start_date <= on_date
        - AND (end_date is None OR end_date >= on_date)
    
    Args:
        trip_id: The ID of the trip.
        on_date: The date to check (YYYY-MM-DD).
    
    Returns:
        list[Participant]: List of active participants on the given date.
    
    Raises:
        ValueError: If input validation fails.
        RuntimeError: If Firestore is not available.
    """
    _validate_non_empty_string(trip_id, "trip_id")
    _validate_date(on_date, "on_date")
    
    # Get all participants and filter in memory
    all_participants = get_participants(trip_id)
    
    active = []
    for p in all_participants:
        # Check if participant has started
        if p.start_date > on_date:
            continue
        # Check if participant has not ended (or ended after on_date)
        if p.end_date is not None and p.end_date < on_date:
            continue
        active.append(p)
    
    return active
