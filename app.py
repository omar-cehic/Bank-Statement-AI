from flask import Flask, render_template, jsonify, request, flash, redirect, url_for, Response, send_file
from database.models import Database
from utils.aws_handler import AWSHandler
from ocr.pdf_processor import PDFProcessor
from ocr.parser import TransactionParser
from categorization.ollama_categorizer import get_spending_summary, get_chat_response
from utils.backup_utils import create_backup, list_backups, restore_backup, get_db_stats
import os
import json
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-key-change-in-production'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size

# Allowed file extensions
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'csv'}

# Categories file path
CATEGORIES_FILE = os.path.join('categorization', 'categories.json')

# Category colors for transaction badges
CATEGORY_COLORS = {
    'Payments': 'success',
    'Fast Food': 'warning',
    'Restaurants': 'info',
    'Gas': 'secondary',
    'Groceries': 'primary',
    'Entertainment': 'dark',
    'Shopping': 'danger',
    'Subscriptions': 'primary',
    'Health': 'danger',
    'Travel': 'success',
    'Other': 'secondary',
    'Uncategorized': 'secondary'
}

# Initialize database, AWS handler, and PDF processor
db = Database()
try:
    aws_handler = AWSHandler()
except Exception as e:
    print(f"Warning: AWS handler initialization failed: {e}")
    aws_handler = None

try:
    pdf_processor = PDFProcessor()
except Exception as e:
    print(f"Warning: PDF processor initialization failed: {e}")
    pdf_processor = None

try:
    transaction_parser = TransactionParser()
except Exception as e:
    print(f"Warning: Transaction parser initialization failed: {e}")
    transaction_parser = None

# Create uploads directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected')
            return redirect(request.url)

        file = request.files['file']
        if file.filename == '':
            flash('No file selected')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

            try:
                # Step 1: Save file locally (temporary)
                file.save(filepath)

                # Step 2: Upload to S3 if AWS handler is available
                s3_key = None
                if aws_handler:
                    upload_result = aws_handler.upload_file(filepath)
                    if upload_result['status'] == 'success':
                        s3_key = upload_result['s3_key']

                        # Step 3: Delete local copy after successful S3 upload
                        try:
                            os.remove(filepath)
                        except Exception as e:
                            print(f"Warning: Failed to delete local file: {e}")
                    else:
                        # S3 upload failed - keep local file and show warning
                        flash(f'File uploaded locally, but S3 upload failed: {upload_result["message"]}', 'warning')

                # Step 4: Record the upload in database
                conn = db.get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO statements (filename, s3_key, processed) VALUES (?, ?, ?)",
                    (filename, s3_key, 0)
                )
                conn.commit()
                conn.close()

                # Success message
                if s3_key:
                    flash(f'File "{filename}" uploaded successfully to cloud storage!', 'success')
                else:
                    flash(f'File "{filename}" uploaded locally (cloud storage unavailable)', 'success')

                return redirect(url_for('upload_file'))

            except Exception as e:
                # Clean up local file if something went wrong
                if os.path.exists(filepath):
                    os.remove(filepath)
                flash(f'Upload failed: {str(e)}', 'error')
                return redirect(url_for('upload_file'))
        else:
            flash('Invalid file type. Please upload PDF, PNG, JPG, JPEG, or CSV files.', 'error')

    return render_template('upload.html')

@app.route('/api/uploaded-files')
def get_uploaded_files():
    """API endpoint to get list of uploaded files (distinct filenames)"""
    conn = db.get_connection()
    cursor = conn.cursor()
    # Get most recent entry for each unique filename with ID for processing
    cursor.execute("""
        SELECT id, filename, upload_date, processed
        FROM statements
        ORDER BY upload_date DESC
        LIMIT 20
    """)
    files = cursor.fetchall()
    conn.close()

    return jsonify({
        'files': [
            {
                'id': file[0],
                'filename': file[1],
                'upload_date': file[2],
                'processed': bool(file[3])
            } for file in files
        ]
    })

@app.route('/api/process-file/<int:file_id>', methods=['POST'])
def process_file(file_id):
    """Process a specific uploaded file"""
    conn = None
    try:
        # Get file info from database
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT filename, s3_key, processed FROM statements WHERE id = ?", (file_id,))
        file_info = cursor.fetchone()

        if not file_info:
            return jsonify({'status': 'error', 'message': 'File not found'})

        filename, s3_key, processed = file_info

        if processed:
            return jsonify({'status': 'error', 'message': 'File already processed'})

        if not s3_key:
            return jsonify({'status': 'error', 'message': 'File not available in cloud storage'})

        if not pdf_processor:
            return jsonify({'status': 'error', 'message': 'PDF processor not available'})

        # Step 1: Extract text from PDF
        result = pdf_processor.extract_text_from_s3_pdf(s3_key)

        if result['status'] == 'success':
            # Step 2: Parse transactions from extracted text
            transactions_result = None
            transaction_count = 0

            if transaction_parser:
                # First, clear any existing transactions for this statement to avoid duplicates
                cursor.execute("DELETE FROM transactions WHERE statement_file = ?", (f"statement_{file_id}",))
                conn.commit()

                # Now parse and store new transactions using the same connection
                transactions_result = transaction_parser.parse_transactions_from_text(
                    result['text'], file_id, conn
                )
                if transactions_result['status'] == 'success':
                    transaction_count = transactions_result['transactions_found']

            # Update database to mark as processed
            cursor.execute("UPDATE statements SET processed = 1 WHERE id = ?", (file_id,))
            conn.commit()

            stored = transactions_result.get('transactions_stored', transaction_count) if transactions_result else transaction_count
            skipped = transactions_result.get('transactions_skipped', 0) if transactions_result else 0
            return jsonify({
                'status': 'success',
                'message': f'Successfully processed {filename}',
                'pages': result['page_count'],
                'characters': result['character_count'],
                'transactions': transaction_count,
                'transactions_stored': stored,
                'transactions_skipped': skipped
            })
        else:
            return jsonify({
                'status': 'error',
                'message': f'Processing failed: {result["message"]}'
            })

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})
    finally:
        if conn:
            conn.close()

@app.route('/transactions/<int:statement_id>')
def view_transactions(statement_id):
    """View transactions for a specific statement"""
    try:
        # Get statement info
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT filename, upload_date, processed FROM statements WHERE id = ?", (statement_id,))
        statement_info = cursor.fetchone()

        if not statement_info:
            flash('Statement not found', 'error')
            return redirect(url_for('upload_file'))

        filename, upload_date, processed = statement_info

        # Get transactions for this statement
        if transaction_parser:
            transactions = transaction_parser.get_transactions_for_statement(statement_id)
        else:
            transactions = []

        conn.close()

        return render_template('transactions.html',
                             statement_id=statement_id,
                             filename=filename,
                             upload_date=upload_date,
                             transactions=transactions,
                             processed=processed,
                             category_colors=CATEGORY_COLORS)

    except Exception as e:
        flash(f'Error loading transactions: {str(e)}', 'error')
        return redirect(url_for('upload_file'))

def _build_spending_context(transactions):
    """Build a compact spending summary string to send to Ollama."""
    purchases = [t for t in transactions if t['amount'] > 0]
    total_spend = sum(t['amount'] for t in purchases)

    # Spending by category — track both amount and count
    category_totals = {}
    category_counts = {}
    for t in purchases:
        cat = t['category'] or 'Uncategorized'
        category_totals[cat] = category_totals.get(cat, 0) + t['amount']
        category_counts[cat] = category_counts.get(cat, 0) + 1

    category_lines = "\n".join(
        f"  - {cat}: ${amt:.2f} ({category_counts[cat]} transaction{'s' if category_counts[cat] != 1 else ''})"
        for cat, amt in sorted(category_totals.items(), key=lambda x: x[1], reverse=True)
    )

    # Top 5 merchants
    merchant_totals = {}
    for t in purchases:
        merchant_totals[t['description']] = merchant_totals.get(t['description'], 0) + t['amount']

    top_merchants = sorted(merchant_totals.items(), key=lambda x: x[1], reverse=True)[:5]
    merchant_lines = "\n".join(f"  - {m}: ${a:.2f}" for m, a in top_merchants)

    return (
        f"Total purchase spend: ${total_spend:.2f}\n\n"
        f"Spending by category:\n{category_lines}\n\n"
        f"Top 5 merchants:\n{merchant_lines}"
    )


@app.route('/reports/<int:statement_id>')
def view_dashboard(statement_id):
    """Analytics dashboard for a statement"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT filename, upload_date FROM statements WHERE id = ?", (statement_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            flash('Statement not found', 'error')
            return redirect(url_for('upload_file'))

        filename, upload_date = row
        transactions = transaction_parser.get_transactions_for_statement(statement_id) if transaction_parser else []

        # Chart data: spending by category
        purchases = [t for t in transactions if t['amount'] > 0]
        category_totals = {}
        for t in purchases:
            cat = t['category'] or 'Uncategorized'
            category_totals[cat] = round(category_totals.get(cat, 0) + t['amount'], 2)
        category_totals = {k: v for k, v in category_totals.items() if v > 0}

        # Chart data: top 10 merchants
        merchant_totals = {}
        for t in purchases:
            merchant_totals[t['description']] = round(
                merchant_totals.get(t['description'], 0) + t['amount'], 2
            )
        top_merchants = sorted(merchant_totals.items(), key=lambda x: x[1], reverse=True)[:10]

        # Chart data: spending by week
        from collections import defaultdict
        from datetime import date
        weekly = defaultdict(float)
        for t in purchases:
            d = date.fromisoformat(t['date'])
            week_label = f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"
            weekly[week_label] = round(weekly[week_label] + t['amount'], 2)
        weekly_sorted = sorted(weekly.items())

        return render_template('reports.html',
            statement_id=statement_id,
            filename=filename,
            upload_date=upload_date,
            category_labels=list(category_totals.keys()),
            category_values=list(category_totals.values()),
            merchant_labels=[m[0] for m in top_merchants],
            merchant_values=[m[1] for m in top_merchants],
            week_labels=[w[0] for w in weekly_sorted],
            week_values=[w[1] for w in weekly_sorted],
        )

    except Exception as e:
        flash(f'Error loading dashboard: {str(e)}', 'error')
        return redirect(url_for('upload_file'))


@app.route('/api/dashboard-summary/<int:statement_id>')
def dashboard_summary(statement_id):
    """Return an AI-generated spending summary for the dashboard"""
    try:
        transactions = transaction_parser.get_transactions_for_statement(statement_id) if transaction_parser else []
        if not transactions:
            return jsonify({'status': 'error', 'message': 'No transactions found'})
        context = _build_spending_context(transactions)
        summary = get_spending_summary(context)
        return jsonify({'status': 'success', 'summary': summary})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/dashboard-chat/<int:statement_id>', methods=['POST'])
def dashboard_chat(statement_id):
    """Answer a user question about their spending"""
    try:
        question = request.json.get('question', '').strip()
        if not question:
            return jsonify({'status': 'error', 'message': 'No question provided'})
        transactions = transaction_parser.get_transactions_for_statement(statement_id) if transaction_parser else []
        if not transactions:
            return jsonify({'status': 'error', 'message': 'No transactions found'})
        context = _build_spending_context(transactions)
        answer = get_chat_response(context, question)
        return jsonify({'status': 'success', 'answer': answer})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/export/<int:statement_id>')
def export_transactions(statement_id):
    """Download transactions for a statement as a CSV file"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT filename FROM statements WHERE id = ?", (statement_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            flash('Statement not found', 'error')
            return redirect(url_for('upload_file'))

        filename = row[0]

        if not transaction_parser:
            flash('Transaction parser not available', 'error')
            return redirect(url_for('view_transactions', statement_id=statement_id))

        transactions = transaction_parser.get_transactions_for_statement(statement_id)

        if not transactions:
            flash('No transactions to export for this statement', 'warning')
            return redirect(url_for('view_transactions', statement_id=statement_id))

        from utils.export_utils import generate_transactions_csv
        csv_string, download_filename = generate_transactions_csv(transactions, filename)

        return Response(
            csv_string,
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename="{download_filename}"'}
        )

    except Exception as e:
        flash(f'Export failed: {str(e)}', 'error')
        return redirect(url_for('view_transactions', statement_id=statement_id))

@app.route('/api/clear-files', methods=['POST'])
def clear_uploaded_files():
    """Clear all uploaded files from database"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM statements")
        cursor.execute("DELETE FROM transactions")  # Also clear transactions
        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'message': 'All files cleared successfully'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/api/update-transaction-category', methods=['POST'])
def update_transaction_category():
    """Update the category of a specific transaction"""
    try:
        data = request.get_json()
        transaction_id = data.get('transaction_id')
        new_category = data.get('category')

        if not transaction_id or not new_category:
            return jsonify({'status': 'error', 'message': 'Missing transaction_id or category'})

        # Update transaction category in database
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE transactions SET category = ? WHERE id = ?", (new_category, transaction_id))

        if cursor.rowcount == 0:
            conn.close()
            return jsonify({'status': 'error', 'message': 'Transaction not found'})

        conn.commit()
        conn.close()

        return jsonify({
            'status': 'success',
            'message': f'Transaction updated to {new_category}',
            'category': new_category
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/api/get-categories')
def get_categories():
    """Get list of all available categories for dropdown"""
    try:
        if transaction_parser and transaction_parser.categorizer:
            categories = transaction_parser.categorizer.list_categories()
            return jsonify({'status': 'success', 'categories': categories})
        else:
            return jsonify({'status': 'error', 'message': 'Categorizer not available'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/api/categories/all')
def get_all_categories():
    """Get all categories with full details (names, descriptions, keywords)"""
    try:
        with open(CATEGORIES_FILE, 'r', encoding='utf-8') as f:
            categories_data = json.load(f)

        return jsonify({
            'status': 'success',
            'categories': categories_data['categories']
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/categories')
def categories():
    """Category management page"""
    return render_template('categories.html')

@app.route('/api/categories/add-keyword', methods=['POST'])
def add_keyword_to_category():
    """Add a keyword to an existing category"""
    try:
        data = request.get_json()
        category_name = data.get('category')
        keyword = data.get('keyword')

        if not category_name or not keyword:
            return jsonify({'status': 'error', 'message': 'Missing category or keyword'})

        # Load current categories
        with open(CATEGORIES_FILE, 'r', encoding='utf-8') as f:
            categories_data = json.load(f)

        # Check if category exists
        if category_name not in categories_data['categories']:
            return jsonify({'status': 'error', 'message': 'Category not found'})

        # Add keyword if not already present
        keywords = categories_data['categories'][category_name]['keywords']
        keyword_lower = keyword.lower()

        if keyword_lower not in [k.lower() for k in keywords]:
            keywords.append(keyword_lower)

            # Save back to file
            with open(CATEGORIES_FILE, 'w', encoding='utf-8') as f:
                json.dump(categories_data, f, indent=2)

            # Reload categorizer
            if transaction_parser and transaction_parser.categorizer:
                transaction_parser.categorizer.reload_categories()

            return jsonify({
                'status': 'success',
                'message': f'Added "{keyword}" to {category_name}',
                'keyword': keyword_lower
            })
        else:
            return jsonify({'status': 'error', 'message': 'Keyword already exists'})

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/api/categories/remove-keyword', methods=['POST'])
def remove_keyword_from_category():
    """Remove a keyword from a category"""
    try:
        data = request.get_json()
        category_name = data.get('category')
        keyword = data.get('keyword')

        if not category_name or not keyword:
            return jsonify({'status': 'error', 'message': 'Missing category or keyword'})

        # Load current categories
        with open(CATEGORIES_FILE, 'r', encoding='utf-8') as f:
            categories_data = json.load(f)

        # Check if category exists
        if category_name not in categories_data['categories']:
            return jsonify({'status': 'error', 'message': 'Category not found'})

        # Remove keyword if present
        keywords = categories_data['categories'][category_name]['keywords']
        keyword_lower = keyword.lower()

        if keyword_lower in keywords:
            keywords.remove(keyword_lower)

            # Save back to file
            with open(CATEGORIES_FILE, 'w', encoding='utf-8') as f:
                json.dump(categories_data, f, indent=2)

            # Reload categorizer
            if transaction_parser and transaction_parser.categorizer:
                transaction_parser.categorizer.reload_categories()

            return jsonify({
                'status': 'success',
                'message': f'Removed "{keyword}" from {category_name}'
            })
        else:
            return jsonify({'status': 'error', 'message': 'Keyword not found'})

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/api/categories/create', methods=['POST'])
def create_category():
    """Create a new category"""
    try:
        data = request.get_json()
        category_name = data.get('name')
        description = data.get('description')
        keywords = data.get('keywords', [])

        if not category_name or not description:
            return jsonify({'status': 'error', 'message': 'Missing name or description'})

        # Load current categories
        with open(CATEGORIES_FILE, 'r', encoding='utf-8') as f:
            categories_data = json.load(f)

        # Check if category already exists
        if category_name in categories_data['categories']:
            return jsonify({'status': 'error', 'message': 'Category already exists'})

        # Create new category
        categories_data['categories'][category_name] = {
            'description': description,
            'keywords': [k.lower().strip() for k in keywords if k.strip()]
        }

        # Save back to file
        with open(CATEGORIES_FILE, 'w', encoding='utf-8') as f:
            json.dump(categories_data, f, indent=2)

        # Reload categorizer
        if transaction_parser and transaction_parser.categorizer:
            transaction_parser.categorizer.reload_categories()

        # Update category colors dictionary
        CATEGORY_COLORS[category_name] = 'info'  # Default color for new categories

        return jsonify({
            'status': 'success',
            'message': f'Created category "{category_name}"',
            'category': {
                'name': category_name,
                'description': description,
                'keywords': categories_data['categories'][category_name]['keywords']
            }
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/health')
def health_check():
    """Health check endpoint to test app and database"""
    db_status = db.test_connection()
    return jsonify({
        'app_status': 'running',
        'database': db_status
    })

@app.route('/settings')
def settings():
    """Settings and backup management page"""
    try:
        stats = get_db_stats()

        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM transactions")
        transaction_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM statements")
        statement_count = cursor.fetchone()[0]
        conn.close()

        ollama_url   = os.environ.get('OLLAMA_URL', 'http://localhost:11434')
        ollama_model = os.environ.get('OLLAMA_MODEL', 'llama3')

        return render_template('settings.html',
            stats=stats,
            transaction_count=transaction_count,
            statement_count=statement_count,
            ollama_url=ollama_url,
            ollama_model=ollama_model,
            backups=list_backups()
        )

    except Exception as e:
        flash(f'Error loading settings: {str(e)}', 'error')
        return redirect(url_for('upload_file'))


@app.route('/api/backup', methods=['POST'])
def backup_database():
    """Create a timestamped backup of the database"""
    try:
        result = create_backup()
        return jsonify(result)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/download-backup')
def download_backup():
    """Serve the live database file as a direct download"""
    try:
        if not os.path.exists('database/database.db'):
            flash('Database file not found', 'error')
            return redirect(url_for('settings'))
        return send_file(
            os.path.abspath('database/database.db'),
            as_attachment=True,
            download_name='database_backup.db',
            mimetype='application/octet-stream'
        )
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/restore-backup', methods=['POST'])
def restore_database():
    """Restore the database from a selected backup file"""
    try:
        data = request.get_json()
        filename = data.get('filename', '').strip()
        if not filename:
            return jsonify({'status': 'error', 'message': 'No filename provided'})
        result = restore_backup(filename)
        return jsonify(result)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/save-settings', methods=['POST'])
def save_settings():
    """Persist Ollama URL and model to .env and apply to current process"""
    try:
        data = request.get_json()
        ollama_url   = data.get('ollama_url', '').strip()
        ollama_model = data.get('ollama_model', '').strip()

        if not ollama_url or not ollama_model:
            return jsonify({'status': 'error', 'message': 'URL and model are required'})

        env_path = '.env'
        env_lines = open(env_path).readlines() if os.path.exists(env_path) else []

        updated_url   = False
        updated_model = False
        for i, line in enumerate(env_lines):
            if line.startswith('OLLAMA_URL='):
                env_lines[i] = f'OLLAMA_URL={ollama_url}\n'
                updated_url = True
            elif line.startswith('OLLAMA_MODEL='):
                env_lines[i] = f'OLLAMA_MODEL={ollama_model}\n'
                updated_model = True

        if not updated_url:   env_lines.append(f'OLLAMA_URL={ollama_url}\n')
        if not updated_model: env_lines.append(f'OLLAMA_MODEL={ollama_model}\n')

        with open(env_path, 'w') as f:
            f.writelines(env_lines)

        # Apply immediately — no restart needed
        os.environ['OLLAMA_URL']   = ollama_url
        os.environ['OLLAMA_MODEL'] = ollama_model

        return jsonify({'status': 'success', 'message': 'Settings saved'})

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)