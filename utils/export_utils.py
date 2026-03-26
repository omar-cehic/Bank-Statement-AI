import csv
import io


def generate_transactions_csv(transactions, filename):
    """
    Generate a CSV file from a list of transaction dictionaries.

    Args:
        transactions (list): List of transaction dicts with keys:
                             date, description, amount, transaction_type, category
        filename (str): Original statement filename, used to name the export

    Returns:
        tuple: (csv_string, download_filename)
               csv_string        — the CSV content as a plain string
               download_filename — suggested filename for the download
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # Header row
    writer.writerow(['Date', 'Description', 'Amount', 'Type', 'Category'])

    for t in transactions:
        # Amount is stored as signed in the DB (negative = credit).
        # Export always positive — the Type column conveys direction.
        amount = abs(t['amount'])
        transaction_type = 'debit' if t['amount'] < 0 else 'credit'

        writer.writerow([
            t['date'],
            t['description'],
            f"{amount:.2f}",
            transaction_type,
            t['category'] or 'Uncategorized',
        ])

    csv_string = output.getvalue()
    output.close()

    # Build a clean download filename from the statement filename
    # e.g. "chase_jan_2026.pdf" -> "chase_jan_2026_transactions.csv"
    base = filename.rsplit('.', 1)[0] if '.' in filename else filename
    download_filename = f"{base}_transactions.csv"

    return csv_string, download_filename
