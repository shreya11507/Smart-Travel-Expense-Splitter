"""
Settlement Module

This module handles the settlement calculations for the travel expense
splitter application.

Features:
    - Convert net balances into settlement transactions
    - Minimize number of transactions using greedy algorithm
    - Handle rounding safely
    - Generate human-readable settlement list

Data Model:
    Input - balances (dict keyed by participant_id):
        - total_paid: float
        - total_share: float
        - net_balance: float (positive = owed money, negative = owes money)
    
    Output - list of settlement transactions:
        - from_participant: string (debtor who pays)
        - to_participant: string (creditor who receives)
        - amount: float (rounded to 2 decimal places)

Functions:
    optimize_settlements: Convert balances into minimal settlement transactions.
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


def optimize_settlements(balances: dict) -> list[dict]:
    """
    Convert net balances into minimal settlement transactions.
    
    Uses a greedy algorithm:
        1. Separate participants into debtors (net_balance < 0) and creditors (net_balance > 0)
        2. Sort debtors by most negative balance (largest debt first)
        3. Sort creditors by most positive balance (largest credit first)
        4. Iteratively match debtors with creditors:
           - Take the largest debtor and largest creditor
           - Settle the minimum of their absolute balances
           - Update remaining balances
           - Repeat until all balances are cleared
    
    Args:
        balances: Dictionary keyed by participant_id containing:
            - total_paid: float
            - total_share: float
            - net_balance: float (positive = owed money, negative = owes money)
    
    Returns:
        list[dict]: List of settlement transactions, each containing:
            - from_participant: string (debtor who pays)
            - to_participant: string (creditor who receives)
            - amount: float (rounded to 2 decimal places)
    
    Notes:
        - Participants with net_balance > 0 receive money
        - Participants with net_balance < 0 pay money
        - Ignores tiny rounding differences (< 0.01)
        - Does NOT modify input balances
        - Does NOT write to Firebase
    """
    # Threshold for ignoring tiny rounding differences
    EPSILON = Decimal("0.01")
    
    # Separate participants into debtors and creditors using Decimal for precision
    # Debtors: net_balance < 0 (they owe money)
    # Creditors: net_balance > 0 (they are owed money)
    debtors = []   # List of (participant_id, amount_owed) - amounts stored as positive
    creditors = [] # List of (participant_id, amount_owed) - amounts stored as positive
    
    for participant_id, balance in balances.items():
        net = Decimal(str(balance["net_balance"]))
        
        if net < -EPSILON:
            # Debtor: owes money (store as positive amount for easier calculation)
            debtors.append([participant_id, abs(net)])
        elif net > EPSILON:
            # Creditor: is owed money
            creditors.append([participant_id, net])
        # Skip participants with zero or near-zero balance
    
    # Sort debtors by largest debt first (descending by amount)
    debtors.sort(key=lambda x: x[1], reverse=True)
    
    # Sort creditors by largest credit first (descending by amount)
    creditors.sort(key=lambda x: x[1], reverse=True)
    
    # List to store settlement transactions
    settlements = []
    
    # Greedy settlement: match largest debtor with largest creditor
    debtor_idx = 0
    creditor_idx = 0
    
    while debtor_idx < len(debtors) and creditor_idx < len(creditors):
        debtor_id, debt_amount = debtors[debtor_idx]
        creditor_id, credit_amount = creditors[creditor_idx]
        
        # Determine settlement amount (minimum of debt and credit)
        settlement_amount = min(debt_amount, credit_amount)
        
        # Skip if settlement amount is negligible (rounding artifact)
        if settlement_amount >= EPSILON:
            # Create settlement transaction
            settlements.append({
                "from_participant": debtor_id,
                "to_participant": creditor_id,
                "amount": _round_decimal(settlement_amount)
            })
        
        # Update remaining balances
        debtors[debtor_idx][1] = debt_amount - settlement_amount
        creditors[creditor_idx][1] = credit_amount - settlement_amount
        
        # Move to next debtor if current one is settled
        if debtors[debtor_idx][1] < EPSILON:
            debtor_idx += 1
        
        # Move to next creditor if current one is settled
        if creditors[creditor_idx][1] < EPSILON:
            creditor_idx += 1
    
    return settlements
