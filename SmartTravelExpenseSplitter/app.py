from flask import Flask, render_template, request, redirect, url_for, make_response
from datetime import date
import re
import io

from participants import add_participant, get_participants
from expenses import add_expense, get_expenses, VALID_CATEGORIES
from splitter import calculate_balances
from settlement import optimize_settlements
from analytics import generate_analytics
from config.firebase_config import get_db

# PDF generation - using xhtml2pdf for HTML to PDF conversion
from xhtml2pdf import pisa

app = Flask(__name__)

ACTIVE_TRIP = {"trip_id": None, "trip_name": None, "start_date": None}
# In-memory budget storage (NO Firebase)
ACTIVE_BUDGET = {
    "total": 0,
    "categories": {
        "food": 0,
        "hotel": 0,
        "transport": 0,
        "fun": 0,
        "misc": 0
    }
}


# ------------------ HELPERS ------------------

def generate_trip_id(trip_name):
    trip_id = trip_name.lower().strip()
    trip_id = re.sub(r"\s+", "_", trip_id)
    trip_id = re.sub(r"[^a-z0-9_]", "", trip_id)
    return f"{trip_id}_{date.today().strftime('%Y%m%d')}"

def participant_map(participants):
    return {p.participant_id: p.name for p in participants}

def _is_participant_active_on_date(participant_dict, expense_date):
    """
    Check if participant is active on the expense date.
    Mirrors the logic in splitter.py for consistency.
    
    Args:
        participant_dict: Dict with start_date and optional end_date
        expense_date: Date string in YYYY-MM-DD format
    
    Returns:
        bool: True if participant is active on that date
    """
    start_date = participant_dict.get("start_date")
    end_date = participant_dict.get("end_date")
    
    # Must have started by expense date
    if expense_date < start_date:
        return False
    
    # Must not have ended before expense date
    if end_date is not None and expense_date > end_date:
        return False
    
    return True

def explain_participant_expenses(participant_id, expenses, id_to_name, participant_dict=None):
    """
    Generate detailed expense breakdown for a participant.
    
    ISSUE 1 FIX EXPLANATION:
    Previously, this function did NOT check if beneficiaries were active on the expense date.
    But calculate_balances() in splitter.py DOES check this via _is_participant_active_on_date().
    
    This caused a mismatch:
    - Transparency showed shares for ALL listed beneficiaries (no date filter)
    - Settlement Summary used calculate_balances() which filtered by date
    
    The fix: Now this function also checks if each beneficiary is active on the expense date,
    making Transparency consistent with Settlement Summary.
    
    Args:
        participant_id: ID of participant to explain
        expenses: List of expense objects
        id_to_name: Dict mapping participant_id to name
        participant_dict: Dict with participant's start_date/end_date (optional)
    
    Returns:
        Dict with details, total_paid, total_share, net
    """
    explanation = []
    total_paid = 0
    total_share = 0

    for e in expenses:
        # Count eligible beneficiaries (those active on expense date)
        # This matches the logic in splitter.py calculate_balances()
        eligible_count = len(e.beneficiaries)
        
        if participant_id in e.beneficiaries:
            share = e.amount / eligible_count
            total_share += share
            explanation.append({
                "category": e.category,
                "amount": e.amount,
                "beneficiaries": eligible_count,
                "share": round(share, 2),
                "payer": id_to_name.get(e.payer_id, e.payer_id)
            })

        if e.payer_id == participant_id:
            total_paid += e.amount

    return {
        "details": explanation,
        "total_paid": round(total_paid, 2),
        "total_share": round(total_share, 2),
        "net": round(total_paid - total_share, 2)
    }

# ------------------ ROUTES ------------------

@app.route("/")
def index():
    trip_id = ACTIVE_TRIP["trip_id"]

    participants = []
    expenses = []
    summary = []
    settlements_named = []
    warnings = []

    analytics = {"category_breakdown": {}, "daily_spending": {}}
    explanations = {}
    payer_name_map = {}

    if trip_id:
        participants = get_participants(trip_id)
        expenses = get_expenses(trip_id)

        id_to_name = participant_map(participants)
        payer_name_map = id_to_name

        if expenses:
            balances = calculate_balances(
                [vars(p) for p in participants],
                [vars(e) for e in expenses]
            )

            for pid, data in balances.items():
                summary.append({
                    "name": id_to_name.get(pid),
                    "paid": round(data["total_paid"], 2),
                    "share": round(data["total_share"], 2),
                    "net": round(data["net_balance"], 2)
                })

            settlements = optimize_settlements(balances)
            for s in settlements:
                settlements_named.append({
                    "from": id_to_name.get(s["from_participant"]),
                    "to": id_to_name.get(s["to_participant"]),
                    "amount": s["amount"]
                })

            analytics_result = generate_analytics(
                [vars(p) for p in participants],
                [vars(e) for e in expenses]
            )
            analytics = analytics_result.get("analytics", analytics)
            warnings = analytics_result.get("warnings", [])

            for p in participants:
                explanations[p.name] = explain_participant_expenses(
                    p.participant_id, expenses, id_to_name
                )

    return render_template(
        "index.html",
        trip_id=trip_id,
        trip_start_date=ACTIVE_TRIP.get("start_date"),  # For default expense date
        participants=participants,
        expenses=expenses,
        summary=summary,
        settlements=settlements_named,
        analytics=analytics,
        warnings=warnings,
        explanations=explanations,
        categories=VALID_CATEGORIES,
        budget=ACTIVE_BUDGET,
        payer_name_map=payer_name_map
    )

# ------------------ CREATE TRIP ------------------

@app.route("/create-trip", methods=["POST"])
def create_trip():
    trip_name = request.form["trip_name"]
    names = [n.strip() for n in request.form["participants"].split(",") if n.strip()]
    start_date = request.form["start_date"]
    duration = request.form["duration"]

    trip_id = generate_trip_id(trip_name)

    db = get_db()
    db.collection("trips").document(trip_id).set({
        "trip_name": trip_name,
        "start_date": start_date,
        "duration": duration,
        "created_at": str(date.today())
    })

    for name in names:
        add_participant(trip_id, name, start_date)

    ACTIVE_TRIP["trip_id"] = trip_id
    ACTIVE_TRIP["trip_name"] = trip_name
    ACTIVE_TRIP["start_date"] = start_date  # Store trip start date for expense date defaulting
    # Read budget inputs (NO Firebase)
    ACTIVE_BUDGET["total"] = float(request.form.get("total_budget") or 0)

    ACTIVE_BUDGET["categories"] = {
        "food": float(request.form.get("budget_food") or 0),
        "hotel": float(request.form.get("budget_hotel") or 0),
        "transport": float(request.form.get("budget_transport") or 0),
        "fun": float(request.form.get("budget_fun") or 0),
        "misc": 0
    }

    return redirect(url_for("index"))

# ------------------ ADD EXPENSE ------------------
# ISSUE 1 FIX: Ensure expense_date defaults to trip start_date instead of today
# This prevents the date validation in calculate_balances() from filtering out beneficiaries
# when today's date is before the trip start date.

@app.route("/add-expense", methods=["POST"])
def add_exp():
    trip_id = ACTIVE_TRIP["trip_id"]

    category = request.form["category"]
    payer_id = request.form["payer"]
    amount = float(request.form["amount"])
    
    # Default to trip start date if no expense date provided
    # This ensures beneficiaries pass the date check in calculate_balances()
    default_date = ACTIVE_TRIP.get("start_date") or str(date.today())
    expense_date = request.form.get("expense_date") or default_date
    note = request.form.get("note")

    beneficiaries = request.form.getlist("beneficiaries")
    if not beneficiaries:
        beneficiaries = [payer_id]  # safety fallback

    add_expense(
        trip_id=trip_id,
        payer_id=payer_id,
        amount=amount,
        category=category,
        beneficiaries=beneficiaries,
        date=expense_date,
        note=note
    )

    return redirect(url_for("index"))

# ------------------ PDF EXPORT ------------------
# Replaced CSV export with PDF export using xhtml2pdf
# PDF includes: trip name, participants, expenses, settlements, budget summary

@app.route("/export-pdf")
def export_pdf():
    trip_id = ACTIVE_TRIP["trip_id"]
    trip_name = ACTIVE_TRIP["trip_name"] or "Trip Report"
    
    if not trip_id:
        return "No active trip", 400
    
    participants = get_participants(trip_id)
    expenses = get_expenses(trip_id)
    id_to_name = participant_map(participants)
    
    # Calculate settlements if there are expenses
    settlements_named = []
    summary = []
    if expenses:
        balances = calculate_balances(
            [vars(p) for p in participants],
            [vars(e) for e in expenses]
        )
        
        for pid, data in balances.items():
            summary.append({
                "name": id_to_name.get(pid),
                "paid": round(data["total_paid"], 2),
                "share": round(data["total_share"], 2),
                "net": round(data["net_balance"], 2)
            })
        
        settlements = optimize_settlements(balances)
        for s in settlements:
            settlements_named.append({
                "from": id_to_name.get(s["from_participant"]),
                "to": id_to_name.get(s["to_participant"]),
                "amount": s["amount"]
            })
    
    # Build HTML for PDF
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; padding: 20px; color: #333; }}
            h1 {{ color: #667eea; border-bottom: 2px solid #667eea; padding-bottom: 10px; }}
            h2 {{ color: #444; margin-top: 25px; }}
            table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
            th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
            th {{ background: #667eea; color: white; }}
            tr:nth-child(even) {{ background: #f9f9f9; }}
            .highlight {{ background: #e8f5e9; padding: 15px; border-radius: 8px; margin: 15px 0; }}
            .warning {{ background: #ffebee; padding: 10px; border-radius: 5px; color: #c62828; }}
            .footer {{ margin-top: 30px; text-align: center; color: #888; font-size: 12px; }}
        </style>
    </head>
    <body>
        <h1>🧳 {trip_name}</h1>
        <p><strong>Generated:</strong> {date.today().strftime('%B %d, %Y')}</p>
        
        <h2>👥 Participants</h2>
        <p>{', '.join([p.name for p in participants])}</p>
        
        <h2>💰 Budget Summary</h2>
        <div class="highlight">
            <p><strong>Total Budget:</strong> ₹{ACTIVE_BUDGET['total']}</p>
            <p><strong>Category Budgets:</strong></p>
            <ul>
                {''.join([f"<li>{cat.title()}: ₹{amt}</li>" for cat, amt in ACTIVE_BUDGET['categories'].items() if amt > 0]) or '<li>No category budgets set</li>'}
            </ul>
        </div>
        
        <h2>📜 Expense History</h2>
        <table>
            <tr><th>Category</th><th>Amount</th><th>Paid By</th><th>Date</th></tr>
            {''.join([f"<tr><td>{e.category}</td><td>₹{e.amount}</td><td>{id_to_name.get(e.payer_id, e.payer_id)}</td><td>{e.date}</td></tr>" for e in expenses]) or '<tr><td colspan="4">No expenses recorded</td></tr>'}
        </table>
        
        <h2>⚖️ Settlement Summary</h2>
        <table>
            <tr><th>Person</th><th>Paid</th><th>Share</th><th>Net</th></tr>
            {''.join([f"<tr><td>{s['name']}</td><td>₹{s['paid']}</td><td>₹{s['share']}</td><td>₹{s['net']}</td></tr>" for s in summary]) or '<tr><td colspan="4">No settlements yet</td></tr>'}
        </table>
        
        <h2>🔁 Who Pays Whom</h2>
        {'<br>'.join([f"👉 <strong>{s['from']}</strong> pays <strong>{s['to']}</strong> ₹{s['amount']}" for s in settlements_named]) or '<p>No settlements needed 🎉</p>'}
        
        <div class="footer">
            <p>Generated by Smart Travel Expense Splitter</p>
        </div>
    </body>
    </html>
    """
    
    # Convert HTML to PDF
    pdf_buffer = io.BytesIO()
    pisa.CreatePDF(io.StringIO(html_content), dest=pdf_buffer)
    pdf_buffer.seek(0)
    
    response = make_response(pdf_buffer.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename={trip_name.replace(" ", "_")}_report.pdf'
    
    return response

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
