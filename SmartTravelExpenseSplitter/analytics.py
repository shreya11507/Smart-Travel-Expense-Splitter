"""
Analytics Module

This module provides analytics and reporting features for the travel expense
splitter application.

Features:
    - Category-wise expense breakdown
    - Daily spending analysis
    - Highest spending day identification
    - Per-participant payer totals
    - Smart warnings for spending imbalances

Data Model:
    Input - participants: list of dicts with:
        - participant_id: string
        - name: string (optional)
    
    Input - expenses: list of dicts with:
        - payer_id: string
        - amount: float
        - category: string
        - date: string (YYYY-MM-DD)
    
    Output - dict containing:
        - analytics: dict with category_breakdown, daily_spending, etc.
        - warnings: list of warning strings

Functions:
    generate_analytics: Generate analytics and warnings from expense data.
"""

from collections import defaultdict
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


def generate_analytics(participants: list[dict], expenses: list[dict]) -> dict:
    """
    Generate analytics and smart warnings from expense data.
    
    Analytics computed:
        - category_breakdown: Total amount spent per category
        - daily_spending: Total amount spent per date
        - highest_spending_day: Date and amount of maximum daily spend
        - payer_totals: Total amount paid by each participant
    
    Warnings generated (rule-based):
        - If one participant paid > 40% of total trip cost
        - If one category > 50% of total spend
        - If a day's spend > 2x average daily spend
    
    Args:
        participants: List of participant dicts with participant_id (name optional).
        expenses: List of expense dicts with payer_id, amount, category, date.
    
    Returns:
        dict: Contains two keys:
            - analytics: dict with category_breakdown, daily_spending,
                         highest_spending_day, payer_totals
            - warnings: list of warning strings
    
    Notes:
        - All amounts rounded to 2 decimal places
        - Uses standard Python (collections, decimal)
        - No Firebase or CLI code
    """
    # Initialize accumulators using Decimal for precision
    category_totals = defaultdict(Decimal)  # category -> total amount
    daily_totals = defaultdict(Decimal)     # date -> total amount
    payer_totals = defaultdict(Decimal)     # payer_id -> total amount
    total_spent = Decimal("0")
    
    # Process each expense
    for expense in expenses:
        amount = Decimal(str(expense["amount"]))
        category = expense["category"]
        date = expense["date"]
        payer_id = expense["payer_id"]
        
        # Accumulate totals
        category_totals[category] += amount
        daily_totals[date] += amount
        payer_totals[payer_id] += amount
        total_spent += amount
    
    # Convert category breakdown to rounded floats
    category_breakdown = {
        category: _round_decimal(amount)
        for category, amount in category_totals.items()
    }
    
    # Convert daily spending to rounded floats
    daily_spending = {
        date: _round_decimal(amount)
        for date, amount in daily_totals.items()
    }
    
    # Find highest spending day
    highest_spending_day = {"date": None, "amount": 0.0}
    if daily_totals:
        max_date = max(daily_totals, key=daily_totals.get)
        highest_spending_day = {
            "date": max_date,
            "amount": _round_decimal(daily_totals[max_date])
        }
    
    # Convert payer totals to rounded floats
    payer_totals_rounded = {
        payer_id: _round_decimal(amount)
        for payer_id, amount in payer_totals.items()
    }
    
    # Build analytics result
    analytics = {
        "category_breakdown": category_breakdown,
        "daily_spending": daily_spending,
        "highest_spending_day": highest_spending_day,
        "payer_totals": payer_totals_rounded
    }
    
    # Generate warnings based on rules
    warnings = []
    total_spent_float = _round_decimal(total_spent)
    
    # Rule 1: If one participant paid > 40% of total trip cost
    if total_spent > 0:
        for payer_id, amount in payer_totals.items():
            percentage = (amount / total_spent) * 100
            if percentage > 40:
                # Find participant name if available
                name = payer_id
                for p in participants:
                    if p["participant_id"] == payer_id and p.get("name"):
                        name = p["name"]
                        break
                warnings.append(
                    f"Warning: {name} paid {_round_decimal(percentage)}% of total expenses "
                    f"(₹{_round_decimal(amount)} of ₹{total_spent_float})"
                )
    
    # Rule 2: If one category > 50% of total spend
    if total_spent > 0:
        for category, amount in category_totals.items():
            percentage = (amount / total_spent) * 100
            if percentage > 50:
                warnings.append(
                    f"Warning: '{category}' accounts for {_round_decimal(percentage)}% of total spend "
                    f"(₹{_round_decimal(amount)} of ₹{total_spent_float})"
                )
    
    # Rule 3: If a day's spend > 2x average daily spend
    if len(daily_totals) > 1:
        # Calculate average daily spend
        avg_daily = total_spent / Decimal(len(daily_totals))
        threshold = avg_daily * 2
        
        for date, amount in daily_totals.items():
            if amount > threshold:
                warnings.append(
                    f"Warning: Spending on {date} (₹{_round_decimal(amount)}) "
                    f"exceeds 2x average daily spend (₹{_round_decimal(avg_daily)})"
                )
    
    return {
        "analytics": analytics,
        "warnings": warnings
    }
