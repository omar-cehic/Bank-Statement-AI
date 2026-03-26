# Bank Statement AI - Development Roadmap

## Overview
This roadmap outlines the 12 core features to be built in 4 phases, each building upon the previous ones. Each feature should be independently testable before moving to the next.

---

## Phase 1: Foundation
*Core infrastructure and basic functionality*

- [x] **Feature 1: Basic Flask App + Database Setup**
  - Create Flask app with basic routing
  - Set up SQLite database with transaction table
  - Create basic HTML template structure with Bootstrap CDN
  - **Test:** App runs, database creates, home page loads

- [x] **Feature 2: File Upload + AWS S3 Integration** *(Completed: 2026-02-20)*
  - Implement file upload form
  - Create AWS S3 handler for upload/download
  - Set up environment configuration with .env
  - **Test:** Upload files to S3 bucket, download them back

- [x] **Feature 3: PDF Text Extraction** *(Completed: 2026-02-21)*
  - Implement pdfplumber-based PDF processing
  - Extract raw text from uploaded bank statement PDFs
  - Display extracted text on web interface
  - **Test:** Upload PDF statement, see extracted text

- [x] **Feature 4: Transaction Parsing** *(Completed: 2026-02-21)*
  - Parse extracted text into structured transaction data
  - Store parsed transactions in SQLite database
  - Display transactions in simple table format
  - **Test:** Upload statement, see parsed transactions in database

---

## Phase 2: Core Processing
*Transaction processing and categorization*

- [x] **Feature 5: Keyword-Based Categorization** *(Completed: 2026-02-25)*
  - Create categories.json with basic expense categories
  - Implement keyword matching for transaction descriptions
  - Update database to store category assignments
  - **Test:** Process statements, verify automatic categorization

- [x] **Feature 6: Manual Category Management** *(Completed: 2026-02-25)*
  - Create web interface to edit transaction categories
  - Implement category management (add/edit/delete categories)
  - Add keyword rule management interface
  - **Test:** Manually recategorize transactions, add new categories

- [ ] **Feature 7: OCR for Image-Based Statements** *(Deferred - Optional)*
  - Add Tesseract OCR processing for image files (JPG/PNG)
  - Integrate with existing transaction parsing pipeline
  - **Test:** Upload scanned statement images, extract and parse transactions
  - **Note:** Requires separate Tesseract installation on Windows with PATH configuration

---

## Phase 3: Intelligence
*AI-powered categorization and validation*

- [x] **Feature 8: Ollama LLM Integration** *(Completed: 2026-03-02)*
  - Set up Ollama with llama3 model
  - Implemented fallback categorization for unmatched transactions
  - Keyword categorizer runs first; Ollama only called on 'Uncategorized' results
  - **Test:** Reprocessed real statement — 38 transactions via keywords, 2 BZOO variants via LLM

- [x] **Feature 9: Data Validation & Reconciliation** *(Completed: 2026-03-03)*
  - Implemented duplicate transaction detection (date + description + amount match)
  - Added stored/skipped counts to processing result and toast notification
  - Fixed upload page to show all statement entries as independent rows
  - Fixed empty transactions page to distinguish duplicates from unprocessed statements
  - **Test:** Reprocessed same statement twice — 38 duplicates correctly skipped on second run

---

## Phase 4: User Experience
*Analytics, export, and data management*

- [x] **Feature 10: Export Functionality** *(Completed: 2026-03-04)*
  - Implemented CSV export for transactions via utils/export_utils.py
  - Added GET /export/<statement_id> route that streams CSV as a file download
  - Added green Export CSV button to transactions page header toolbar
  - Columns: Date, Description, Amount, Type, Category — amounts always positive, Type = Credit/Debit
  - **Test:** Downloaded CSV for real statement — 38 rows, correct columns, correct Credit/Debit labels

- [x] **Feature 11: Basic Analytics Dashboard** *(Completed: 2026-03-04)*
  - Built analytics dashboard with three Chart.js charts (category donut, merchant bar, weekly bar)
  - Added auto-generated AI spending summary via Ollama on page load
  - Added single-question AI chat grounded in actual transaction data (totals + counts per category)
  - Added View Dashboard button to transactions page toolbar
  - **Test:** All three charts render correctly; AI correctly answered count, single-purchase, and percentage questions

- [x] **Feature 12: Backup & Settings** *(Completed: 2026-03-24)*
  - Built utils/backup_utils.py with create, list, restore, and stats functions
  - Added /settings page with database stats panel, backup/restore UI, and Ollama config fields
  - Implemented Bootstrap modal confirmation for restore (no native browser dialogs)
  - Ollama URL and model now read from environment variables with hardcoded fallbacks
  - **Test:** All five scenarios passed — backup, download, restore modal, stats panel, settings pre-population

---

## Progress Tracking
- **Phase 1 Complete:** ✅ (4/4 features)
- **Phase 2 Complete:** ⬜ (2/3 features)
- **Phase 3 Complete:** ✅ (2/2 features)
- **Phase 4 Complete:** ✅ (3/3 features)

**Overall Progress:** 11/12 features complete (92%) — Feature 7 deferred (OCR/Tesseract optional)

---

## Notes
- Each feature must be fully tested and working before proceeding to the next
- Update this roadmap by checking off completed features
- If scope changes are needed, document them in the project notes below

### Project Notes
*Add any scope changes, blockers, or important decisions here as development progresses*