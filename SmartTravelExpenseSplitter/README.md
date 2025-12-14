# SmartTravelExpenseSplitter

A CLI-based travel expense splitting application with Firebase Firestore backend.

## Features

- **Participant Management**: Add, update, and manage trip participants
- **Expense Tracking**: Record and categorize travel expenses
- **Smart Splitting**: Split expenses equally, by percentage, or custom amounts
- **Settlement Calculation**: Calculate who owes whom with minimized transactions
- **Analytics**: View expense summaries and breakdowns
- **Cloud Storage**: Firebase Firestore for data persistence

## Requirements

- Python 3.10+
- Firebase account with Firestore enabled

## Project Structure

```
SmartTravelExpenseSplitter/
│
├── main.py              # Application entry point
├── participants.py      # Participant management
├── expenses.py          # Expense tracking
├── splitter.py          # Expense splitting logic
├── settlement.py        # Settlement calculations
├── analytics.py         # Analytics and reporting
├── firebase_store.py    # Firebase Firestore operations
├── config/
│   └── firebase_config.py  # Firebase configuration
├── utils.py             # Utility functions
└── README.md            # This file
```

## Installation

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install firebase-admin
   ```
3. Configure Firebase credentials in `config/firebase_config.py`

## Usage

```bash
python main.py [command] [options]
```

## Configuration

Set up your Firebase credentials:

1. Create a Firebase project at https://console.firebase.google.com
2. Enable Firestore database
3. Download service account credentials
4. Update `config/firebase_config.py` with your project details

## License

MIT License
