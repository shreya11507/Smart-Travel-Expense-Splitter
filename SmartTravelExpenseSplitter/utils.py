"""
Utilities Module

This module provides utility functions and helpers for the travel expense
splitter application.

Features:
    - Transparency and traceability of cost calculations
    - Per-participant expense breakdown explanations
    - Date/time formatting
    - Currency conversion helpers

Data Model:
    Input - participants: list of dicts with:
        - participant_id: string
        - start_date: string (YYYY-MM-DD)
        - end_date: string or None
    
    Input - expenses: list of dicts with:
        - expense_id: string (optional)
        - payer_id: string
        - amount: float
        - category: string
        - beneficiaries: list of participant_ids
        - date: string (YYYY-MM-DD)
    
    Input - balances: dict from calculate_balances() with:
        - total_paid: float
        - total_share: float
        - net_balance: float

Functions:
    explain_participant_share: Get detailed breakdown for one participant.
    explain_all_participants: Get detailed breakdown for all participants.
    format_currency: Format amount with currency symbol.
    validate_amount: Validate if input is a valid monetary amount.
    format_date: Format date for consistent display.
    generate_id: Generate a unique identifier for records.
"""

from decimal import Decimal, ROUND_HALF_UP


def _round_decimal(value: Decimal) -> float:
    """
    Round a Decimal to 2 decimal places and convert to float.
    
    Args:
        value: Decimal value to round.
    
    Returns:
        float: Rounded value as float.
    """
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _is_participant_active_on_date(participant: dict, date: str) -> bool:
    """
    Check if a participant is active on a given date.
    
    Reuses the same eligibility logic from splitter.py:
        - date >= participant.start_date
        - AND (participant.end_date is None OR date <= participant.end_date)
    
    Args:
        participant: Participant dict with start_date and optional end_date.
        date: Date string in YYYY-MM-DD format.
    
    Returns:
        bool: True if participant is active on the date.
    """
    start_date = participant.get("start_date")
    end_date = participant.get("end_date")
    
    # Check if participant has started by the expense date
    if date < start_date:
        return False
    
    # Check if participant has not ended (or ended on/after expense date)
    if end_date is not None and date > end_date:
        return False
    
    return True


def _get_eligible_beneficiaries(expense: dict, participant_map: dict) -> list[str]:
    """
    Get list of eligible beneficiaries for an expense.
    
    A beneficiary is eligible if:
        - They are in the expense's beneficiaries list
        - They are active on the expense date (based on start/end dates)
    
    Args:
        expense: Expense dict with beneficiaries and date.
        participant_map: Dict mapping participant_id to participant dict.
    
    Returns:
        list[str]: List of eligible participant IDs.
    """
    beneficiaries = expense.get("beneficiaries", [])
    expense_date = expense.get("date")
    
    eligible = []
    for beneficiary_id in beneficiaries:
        if beneficiary_id not in participant_map:
            continue
        participant = participant_map[beneficiary_id]
        if _is_participant_active_on_date(participant, expense_date):
            eligible.append(beneficiary_id)
    
    return eligible


def explain_participant_share(
    participant_id: str,
    participants: list[dict],
    expenses: list[dict],
    balances: dict
) -> dict:
    """
    Generate detailed explanation of how a participant's share was calculated.
    
    For each expense where the participant was an eligible beneficiary:
        - Shows expense details (id, category, date, total amount)
        - Shows all beneficiaries for that expense
        - Shows the participant's share (amount / num_eligible_beneficiaries)
    
    Args:
        participant_id: ID of the participant to explain.
        participants: List of participant dicts.
        expenses: List of expense dicts.
        balances: Output from calculate_balances().
    
    Returns:
        dict: Explanation containing:
            - participant_id: string
            - expense_contributions: list of dicts with expense breakdown
            - total_share: float (sum of all contributions)
            - total_paid: float (from balances)
            - net_balance: float (from balances)
    
    Notes:
        - Only includes expenses where participant was eligible beneficiary
        - Respects start_date and end_date rules
        - Amounts rounded to 2 decimal places
    """
    # Build participant lookup map
    participant_map = {p["participant_id"]: p for p in participants}
    
    # Get participant's balance info (default to zeros if not found)
    balance_info = balances.get(participant_id, {
        "total_paid": 0.0,
        "total_share": 0.0,
        "net_balance": 0.0
    })
    
    # Check if participant exists
    if participant_id not in participant_map:
        return {
            "participant_id": participant_id,
            "expense_contributions": [],
            "total_share": 0.0,
            "total_paid": 0.0,
            "net_balance": 0.0,
            "error": f"Participant {participant_id} not found"
        }
    
    participant = participant_map[participant_id]
    
    # Build list of expense contributions for this participant
    expense_contributions = []
    calculated_total_share = Decimal("0")
    
    for expense in expenses:
        expense_date = expense.get("date")
        beneficiaries = expense.get("beneficiaries", [])
        
        # Skip if participant is not in beneficiaries list
        if participant_id not in beneficiaries:
            continue
        
        # Skip if participant is not active on expense date
        if not _is_participant_active_on_date(participant, expense_date):
            continue
        
        # Get all eligible beneficiaries for this expense
        eligible_beneficiaries = _get_eligible_beneficiaries(expense, participant_map)
        
        # Skip if no eligible beneficiaries (shouldn't happen, but safety check)
        if len(eligible_beneficiaries) == 0:
            continue
        
        # Calculate this participant's share of the expense
        expense_amount = Decimal(str(expense.get("amount", 0)))
        share_per_person = expense_amount / Decimal(len(eligible_beneficiaries))
        
        # Build contribution record
        contribution = {
            "expense_id": expense.get("expense_id", "N/A"),
            "category": expense.get("category", "unknown"),
            "date": expense_date,
            "total_expense_amount": _round_decimal(expense_amount),
            "beneficiaries": eligible_beneficiaries,
            "num_beneficiaries": len(eligible_beneficiaries),
            "participant_share": _round_decimal(share_per_person)
        }
        
        expense_contributions.append(contribution)
        calculated_total_share += share_per_person
    
    # Build final explanation
    return {
        "participant_id": participant_id,
        "expense_contributions": expense_contributions,
        "total_share": balance_info["total_share"],
        "total_paid": balance_info["total_paid"],
        "net_balance": balance_info["net_balance"]
    }


def explain_all_participants(
    participants: list[dict],
    expenses: list[dict],
    balances: dict
) -> list[dict]:
    """
    Generate detailed explanations for all participants.
    
    Calls explain_participant_share for each participant and returns
    a list of explanations.
    
    Args:
        participants: List of participant dicts.
        expenses: List of expense dicts.
        balances: Output from calculate_balances().
    
    Returns:
        list[dict]: List of explanation dicts, one per participant.
    
    Notes:
        - Includes all participants, even those with no expenses
        - Ordered by participant_id
    """
    explanations = []
    
    for participant in participants:
        participant_id = participant["participant_id"]
        explanation = explain_participant_share(
            participant_id=participant_id,
            participants=participants,
            expenses=expenses,
            balances=balances
        )
        explanations.append(explanation)
    
    # Sort by participant_id for consistent ordering
    explanations.sort(key=lambda x: x["participant_id"])
    
    return explanations


def format_currency(amount: float, symbol: str = "₹") -> str:
    """
    Format a monetary amount with the appropriate currency symbol.
    
    Args:
        amount: The amount to format.
        symbol: Currency symbol (default: ₹).
    
    Returns:
        str: Formatted string like "₹1,234.56".
    """
    return f"{symbol}{amount:,.2f}"


def validate_amount(value) -> bool:
    """
    Validate if the input is a valid monetary amount.
    
    Args:
        value: Value to validate.
    
    Returns:
        bool: True if valid positive number.
    """
    try:
        amount = float(value)
        return amount > 0
    except (TypeError, ValueError):
        return False


def format_date(date_str: str) -> str:
    """
    Format a date for consistent display.
    
    Args:
        date_str: Date string in YYYY-MM-DD format.
    
    Returns:
        str: Formatted date string.
    """
    # Simple pass-through for now; can be enhanced for locale-specific formatting
    return date_str


def generate_id(prefix: str = "ID", number: int = 1) -> str:
    """
    Generate a formatted identifier.
    
    Args:
        prefix: Prefix for the ID (e.g., "P", "E").
        number: Numeric value to format.
    
    Returns:
        str: Formatted ID like "P001", "E042".
    """
    return f"{prefix}{number:03d}"
