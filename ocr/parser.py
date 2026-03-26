import re
import sys
import os
from datetime import datetime
from decimal import Decimal

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from database.models import Database
from categorization.keyword_categorizer import KeywordCategorizer
from categorization.ollama_categorizer import categorize_with_ollama

class TransactionParser:
    def __init__(self):
        self.db = Database()

        # Initialize the categorizer
        try:
            self.categorizer = KeywordCategorizer()
        except Exception as e:
            print(f"Warning: Failed to initialize categorizer: {e}")
            self.categorizer = None

        # Ollama is a stateless function — no init needed, imported directly

        # Transaction patterns for Chase Freedom Unlimited statements
        self.transaction_patterns = [
            # Date format: MM/DD followed by merchant and amount
            # Example: "12/24 PANDA EXPRESS #2927 NILES IL 39.72"
            r'(\d{1,2}/\d{1,2})\s+(.+?)\s+(\d+\.\d{2})$',

            # Payment pattern with negative amount
            # Example: "01/02 Payment Thank You-Mobile -1,008.45"
            r'(\d{1,2}/\d{1,2})\s+(.+?)\s+(-\d{1,3}(?:,\d{3})*\.\d{2})$',

            # Alternative pattern with price at end
            # Example: "12/24 SSA BROOKFIELD ZOO BROOKFIELD IL 10.52"
            r'(\d{1,2}/\d{1,2})\s+(.+?)\s+(\d{1,3}(?:,\d{3})*\.\d{2})$'
        ]

    def parse_transactions_from_text(self, raw_text, statement_id=None, conn=None):
        """
        Parse raw PDF text and extract individual transactions

        Args:
            raw_text (str): Raw text extracted from PDF
            statement_id (int): Optional statement ID to link transactions
            conn: Optional database connection to use

        Returns:
            dict: Result containing parsed transactions or error
        """
        try:
            transactions = []
            lines = raw_text.split('\n')

            # Look for the transaction section
            in_transaction_section = False

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Detect start of transaction sections
                if 'PAYMENTS AND OTHER CREDITS' in line or 'PURCHASE' in line:
                    in_transaction_section = True
                    continue

                # Skip section headers and end markers
                if line in ['PAYMENTS AND OTHER CREDITS', 'PURCHASE', 'PURCHASES']:
                    continue

                # Stop at certain sections
                if any(section in line for section in [
                    '2026 Totals Year-to-Date',
                    'INTEREST CHARGES',
                    'Your Annual Percentage Rate',
                    'Page',
                    '--- PAGE'
                ]):
                    in_transaction_section = False
                    continue

                # Parse transaction lines
                if in_transaction_section:
                    transaction = self._parse_transaction_line(line)
                    if transaction:
                        transactions.append(transaction)

            # Store in database if statement_id provided
            if statement_id and transactions:
                stored_count, skipped_count = self._store_transactions(transactions, statement_id, conn)
                return {
                    'status': 'success',
                    'message': f'Successfully parsed {len(transactions)} transactions',
                    'transactions_found': len(transactions),
                    'transactions_stored': stored_count,
                    'transactions_skipped': skipped_count,
                    'transactions': transactions
                }
            else:
                return {
                    'status': 'success',
                    'message': f'Successfully parsed {len(transactions)} transactions',
                    'transactions_found': len(transactions),
                    'transactions': transactions
                }

        except Exception as e:
            return {
                'status': 'error',
                'message': f'Failed to parse transactions: {str(e)}',
                'error_type': 'parsing_error'
            }

    def _parse_transaction_line(self, line):
        """Parse a single line to extract transaction details"""
        for pattern in self.transaction_patterns:
            match = re.match(pattern, line)
            if match:
                date_str = match.group(1)
                description = match.group(2).strip()
                amount_str = match.group(3)

                # Skip invalid descriptions (too short, likely headers)
                if len(description) < 3:
                    continue

                # Skip lines that look like headers or totals
                if any(skip in description.upper() for skip in [
                    'DATE OF', 'MERCHANT NAME', 'TRANSACTION DESCRIPTION',
                    '$', 'AMOUNT', 'TOTAL', 'BALANCE', 'YEAR-TO-DATE'
                ]):
                    continue

                try:
                    # Parse amount (remove commas, handle negatives)
                    amount = Decimal(amount_str.replace(',', ''))

                    # Determine transaction type
                    transaction_type = 'credit' if amount < 0 else 'debit'

                    # Parse date (assume current year if not specified)
                    current_year = datetime.now().year
                    if '/' in date_str:
                        month, day = date_str.split('/')
                        transaction_date = f"{current_year}-{month.zfill(2)}-{day.zfill(2)}"
                    else:
                        continue  # Skip if date format is unexpected

                    # Categorize the transaction — keyword first, Ollama fallback
                    category = 'Uncategorized'
                    if self.categorizer:
                        category = self.categorizer.categorize_transaction(description)

                    if category == 'Uncategorized':
                        print(f"  [Ollama] Keyword miss — asking LLM: '{description}'")
                        category = categorize_with_ollama(description)

                    return {
                        'date': transaction_date,
                        'description': description,
                        'amount': float(abs(amount)),  # Store as positive, use type for sign
                        'transaction_type': transaction_type,
                        'category': category,
                        'raw_line': line
                    }

                except (ValueError, IndexError) as e:
                    # Skip lines that don't parse properly
                    continue

        return None

    def _store_transactions(self, transactions, statement_id, conn=None):
        """
        Store parsed transactions in database

        Args:
            transactions: List of transaction dictionaries
            statement_id: ID of the statement
            conn: Optional database connection to use. If None, creates its own.

        Returns:
            tuple: (stored_count, skipped_count)
        """
        try:
            # Use provided connection or create new one
            if conn is not None:
                cursor = conn.cursor()
                should_close_conn = False
            else:
                conn = self.db.get_connection()
                cursor = conn.cursor()
                should_close_conn = True

            stored_count = 0
            skipped_count = 0
            for transaction in transactions:
                signed_amount = transaction['amount'] if transaction['transaction_type'] == 'debit' else -transaction['amount']

                if self.db.transaction_exists(transaction['date'], transaction['description'], signed_amount, conn):
                    print(f"  [Duplicate] Skipped: {transaction['date']} {transaction['description']} ${signed_amount}")
                    skipped_count += 1
                    continue

                cursor.execute("""
                    INSERT INTO transactions
                    (date, description, amount, category, statement_file, created_at)
                    VALUES (?, ?, ?, ?, ?, datetime('now'))
                """, (
                    transaction['date'],
                    transaction['description'],
                    signed_amount,
                    transaction['category'],
                    f"statement_{statement_id}"
                ))
                stored_count += 1

            conn.commit()

            # Only close if we created the connection ourselves
            if should_close_conn:
                conn.close()

            return stored_count, skipped_count

        except Exception as e:
            print(f"Error storing transactions: {e}")
            return 0, 0

    def get_transactions_for_statement(self, statement_id):
        """Retrieve all transactions for a specific statement"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, date, description, amount, category
                FROM transactions
                WHERE statement_file = ?
                ORDER BY date DESC
            """, (f"statement_{statement_id}",))

            transactions = cursor.fetchall()
            conn.close()

            return [
                {
                    'id': t[0],
                    'date': t[1],
                    'description': t[2],
                    'amount': t[3],
                    'category': t[4]
                } for t in transactions
            ]

        except Exception as e:
            print(f"Error retrieving transactions: {e}")
            return []


def test_transaction_parsing():
    """Test transaction parsing with sample text"""
    print("Transaction Parser Test")
    print("=" * 50)

    # Get statement ID from command line or prompt
    if len(sys.argv) > 1:
        statement_id = int(sys.argv[1])
        print(f"Using statement ID from command line: {statement_id}")
    else:
        try:
            statement_id = int(input("Enter statement ID to test parsing (or 0 to test without storing): "))
        except (ValueError, EOFError):
            print("No input provided. Using test mode without database storage.")
            statement_id = 0

    # Get the raw text from a processed statement
    db = Database()
    if statement_id > 0:
        try:
            # Try to get processed text from database or use OCR processor
            from ocr.pdf_processor import PDFProcessor

            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT filename, s3_key FROM statements WHERE id = ?", (statement_id,))
            statement_info = cursor.fetchone()
            conn.close()

            if not statement_info:
                print("Statement not found!")
                return

            filename, s3_key = statement_info
            print(f"Processing statement: {filename}")

            # Extract text using PDF processor
            pdf_processor = PDFProcessor()
            result = pdf_processor.extract_text_from_s3_pdf(s3_key)

            if result['status'] != 'success':
                print(f"Failed to extract text: {result['message']}")
                return

            raw_text = result['text']

        except Exception as e:
            print(f"Error loading statement: {e}")
            return
    else:
        # Use sample transaction text for testing
        raw_text = """
        PAYMENTS AND OTHER CREDITS
        01/02 Payment Thank You-Mobile -1,008.45

        PURCHASE
        12/24 SSA BROOKFIELD ZOO BROOKFIELD IL 10.52
        12/24 PANDA EXPRESS #2927 NILES IL 39.72
        12/24 MCDONALD'S F1715 DES PLAINES IL 12.24
        12/25 DD/BR #306011 Q35 877-390-0277 IL 11.17
        01/09 CLAUDE.AI SUBSCRIPTION ANTHROPIC.COM CA 20.00
        01/09 UNCLE JULIO'S 022 SKOKIE IL 77.55
        """

    # Parse transactions
    parser = TransactionParser()
    result = parser.parse_transactions_from_text(raw_text, statement_id if statement_id > 0 else None)

    print(f"\nStatus: {result['status'].upper()}")
    print(f"Message: {result['message']}")

    if result['status'] == 'success':
        print(f"Transactions found: {result['transactions_found']}")
        if 'transactions_stored' in result:
            print(f"Transactions stored: {result['transactions_stored']}")

        print("\n" + "=" * 50)
        print("PARSED TRANSACTIONS:")
        print("=" * 50)

        for i, transaction in enumerate(result['transactions'], 1):
            trans_type = "[CREDIT]" if transaction['transaction_type'] == 'credit' else "[DEBIT]"
            print(f"{i}. {transaction['date']} - {trans_type}")
            print(f"   Description: {transaction['description']}")
            print(f"   Amount: ${transaction['amount']:.2f}")
            print(f"   Category: {transaction['category']}")
            print(f"   Raw: {transaction['raw_line']}")
            print()
    else:
        print(f"Error: {result.get('error_type', 'Unknown')}")

    print("Test completed.")


# Allow running this file directly to test parsing
if __name__ == "__main__":
    test_transaction_parsing()