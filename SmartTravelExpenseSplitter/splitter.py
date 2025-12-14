"""
Splitter Module

This module handles the expense splitting logic for the travel expense
splitter application.

Features:
    - Equal splitting among beneficiaries
    - Per-participant balance calculation
    - Support for mid-trip joins/leaves
    - Decimal-safe rounding

Data Model:
    Input - participants (list of dicts):
        - participant_id: string
        - start_date: string (YYYY-MM-DD)
        - end_date: string or None
    
    Input - expenses (list of dicts):
        - payer_id: string
        - amount: float
        - beneficiaries: list of participant_ids
        - date: string (YYYY-MM-DD)
    
    Output - balances (dict keyed by participant_id):
        - total_paid: float (sum of expenses paid by this participant)
        - total_share: float (sum of shares owed by this participant)
        - net_balance: float (total_paid - total_share)

Functions:
    calculate_balances: Calculate per-participant financial balances.
"""

from decimal import Decimal, ROUND_HALF_UP


def _is_participant_active_on_date(participant: dict, date: str) -> bool:
    """
    Check if a participant is active on a given date.
    
    A participant is active if:
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


def _round_decimal(value: Decimal) -> float:
    """
    Round a Decimal to 2 decimal places and convert to float.
    
    Uses ROUND_HALF_UP for consistent banker's rounding.
    
    Args:
        value: Decimal value to round.
    
    Returns:
        float: Rounded value as float.
    """
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def calculate_balances(participants: list[dict], expenses: list[dict]) -> dict:
    """
    Calculate per-participant financial balances from expenses.
    
    For each expense:
        1. The payer's total_paid increases by the expense amount
        2. Each eligible beneficiary's total_share increases by (amount / num_beneficiaries)
    
    Eligibility rules:
        - A beneficiary must be in the expense's beneficiaries list
        - A beneficiary must be active on the expense date (based on start/end dates)
    
    Args:
        participants: List of participant dicts with:
            - participant_id: string
            - start_date: string (YYYY-MM-DD)
            - end_date: string or None
        expenses: List of expense dicts with:
            - payer_id: string
            - amount: float
            - beneficiaries: list of participant_ids
            - date: string (YYYY-MM-DD)
    
    Returns:
        dict: Dictionary keyed by participant_id containing:
            - total_paid: float (sum of all expenses paid)
            - total_share: float (sum of all shares owed)
            - net_balance: float (total_paid - total_share)
                - Positive = participant is owed money
                - Negative = participant owes money
    
    Notes:
        - Payer does NOT need to be a beneficiary
        - Uses Decimal for precision, rounds to 2 decimal places
        - Does NOT write to Firebase
    """
    # Build a lookup map for participants by ID for quick access
    participant_map = {p["participant_id"]: p for p in participants}
    
    # Initialize balances for all participants with zero values
    # Using Decimal for precision during calculations
    balances = {
        p["participant_id"]: {
            "total_paid": Decimal("0"),
            "total_share": Decimal("0")
        }
        for p in participants
    }
    
    # Process each expense
    for expense in expenses:
        payer_id = expense["payer_id"]
        amount = Decimal(str(expense["amount"]))  # Convert to Decimal for precision
        beneficiaries = expense["beneficiaries"]
        expense_date = expense["date"]
        
        # Add to payer's total_paid (payer must exist in participants)
        if payer_id in balances:
            balances[payer_id]["total_paid"] += amount
        
        # Determine eligible beneficiaries (must be active on expense date)
        eligible_beneficiaries = []
        for beneficiary_id in beneficiaries:
            # Check if beneficiary exists in participants
            if beneficiary_id not in participant_map:
                continue
            
            # Check if beneficiary is active on the expense date
            participant = participant_map[beneficiary_id]
            if _is_participant_active_on_date(participant, expense_date):
                eligible_beneficiaries.append(beneficiary_id)
        
        # Skip if no eligible beneficiaries (avoid division by zero)
        if len(eligible_beneficiaries) == 0:
            continue
        
        # Calculate per-person share (equal split among eligible beneficiaries)
        share_per_person = amount / Decimal(len(eligible_beneficiaries))
        
        # Add share to each eligible beneficiary's total_share
        for beneficiary_id in eligible_beneficiaries:
            balances[beneficiary_id]["total_share"] += share_per_person
    
    # Calculate net_balance and round all values to 2 decimal places
    result = {}
    for participant_id, balance in balances.items():
        total_paid = _round_decimal(balance["total_paid"])
        total_share = _round_decimal(balance["total_share"])
        net_balance = _round_decimal(balance["total_paid"] - balance["total_share"])
        
        result[participant_id] = {
            "total_paid": total_paid,
            "total_share": total_share,
            "net_balance": net_balance
        }
    
    return result
