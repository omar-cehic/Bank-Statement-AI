import pdfplumber
import os
import sys
import tempfile
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.aws_handler import AWSHandler

# Load environment variables
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(env_path)

class PDFProcessor:
    def __init__(self):
        try:
            self.aws_handler = AWSHandler()
        except Exception as e:
            print(f"Warning: AWS handler not available: {e}")
            self.aws_handler = None

    def extract_text_from_s3_pdf(self, s3_key):
        """
        Download PDF from S3, extract text, and delete local copy

        Args:
            s3_key (str): S3 object key for the PDF file

        Returns:
            dict: Result containing extracted text or error message
        """
        if not self.aws_handler:
            return {
                'status': 'error',
                'message': 'AWS S3 connection not available',
                'error_type': 'aws_unavailable'
            }

        # Create temporary file for download
        temp_file = None
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp:
                temp_file = temp.name

            # Download from S3
            download_result = self.aws_handler.download_file(s3_key, temp_file)
            if download_result['status'] != 'success':
                return {
                    'status': 'error',
                    'message': f'Failed to download from S3: {download_result["message"]}',
                    'error_type': 'download_failed'
                }

            # Extract text from PDF
            text_result = self.extract_text_from_local_pdf(temp_file)

            return text_result

        except Exception as e:
            return {
                'status': 'error',
                'message': f'PDF processing failed: {str(e)}',
                'error_type': 'processing_failed'
            }
        finally:
            # Clean up temporary file
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception as e:
                    print(f"Warning: Failed to delete temporary file {temp_file}: {e}")

    def extract_text_from_local_pdf(self, pdf_path):
        """
        Extract text from a local PDF file using pdfplumber

        Args:
            pdf_path (str): Path to the local PDF file

        Returns:
            dict: Result containing extracted text or error message
        """
        try:
            if not os.path.exists(pdf_path):
                return {
                    'status': 'error',
                    'message': f'File not found: {pdf_path}',
                    'error_type': 'file_not_found'
                }

            extracted_text = ""
            page_count = 0

            with pdfplumber.open(pdf_path) as pdf:
                if len(pdf.pages) == 0:
                    return {
                        'status': 'error',
                        'message': 'PDF contains no pages',
                        'error_type': 'empty_pdf'
                    }

                for page_num, page in enumerate(pdf.pages, 1):
                    try:
                        page_text = page.extract_text()
                        if page_text:
                            extracted_text += f"\n--- PAGE {page_num} ---\n"
                            extracted_text += page_text
                            page_count += 1
                        else:
                            # Try to extract tables if no text found
                            tables = page.extract_tables()
                            if tables:
                                extracted_text += f"\n--- PAGE {page_num} (TABLE DATA) ---\n"
                                for table in tables:
                                    for row in table:
                                        if row:
                                            row_text = " | ".join([str(cell) if cell else "" for cell in row])
                                            extracted_text += row_text + "\n"
                                page_count += 1
                            else:
                                print(f"Warning: Page {page_num} contains no extractable text (likely scanned image)")

                    except Exception as e:
                        print(f"Warning: Failed to extract text from page {page_num}: {e}")
                        continue

            if not extracted_text.strip():
                return {
                    'status': 'error',
                    'message': 'No text could be extracted from PDF. This may be a scanned document requiring OCR.',
                    'error_type': 'no_text_extracted'
                }

            return {
                'status': 'success',
                'message': f'Successfully extracted text from {page_count} pages',
                'text': extracted_text.strip(),
                'page_count': page_count,
                'character_count': len(extracted_text.strip())
            }

        except pdfplumber.pdf.PDFSyntaxError:
            return {
                'status': 'error',
                'message': 'PDF file is corrupted or invalid',
                'error_type': 'corrupted_pdf'
            }
        except PermissionError:
            return {
                'status': 'error',
                'message': 'PDF is password protected. Please provide an unprotected copy.',
                'error_type': 'password_protected'
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Failed to process PDF: {str(e)}',
                'error_type': 'processing_error'
            }


def test_pdf_extraction():
    """Test PDF extraction from command line"""
    print("PDF Text Extraction Test")
    print("=" * 50)

    # Check if S3 key provided as command line argument
    if len(sys.argv) > 1:
        s3_key = sys.argv[1]
        print(f"Using S3 key from command line: {s3_key}")
    else:
        # Get S3 key from user input
        try:
            s3_key = input("Enter S3 key of PDF file to test (e.g., 'statements/2026/02/20/your-statement.pdf'): ")
        except EOFError:
            print("No input provided. Please run with: py ocr/pdf_processor.py <s3_key>")
            return

    if not s3_key.strip():
        print("No S3 key provided. Please run with: py ocr/pdf_processor.py <s3_key>")
        return

    processor = PDFProcessor()
    result = processor.extract_text_from_s3_pdf(s3_key.strip())

    print(f"\nStatus: {result['status'].upper()}")
    print(f"Message: {result['message']}")

    if result['status'] == 'success':
        print(f"Pages processed: {result['page_count']}")
        print(f"Characters extracted: {result['character_count']}")
        print("\n" + "=" * 50)
        print("EXTRACTED TEXT:")
        print("=" * 50)
        print(result['text'])
        print("=" * 50)
    else:
        print(f"Error type: {result['error_type']}")

    print("\nTest completed.")


# Allow running this file directly to test extraction
if __name__ == "__main__":
    test_pdf_extraction()