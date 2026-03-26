import boto3
from botocore.exceptions import ClientError, NoCredentialsError, BotoCoreError
import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
# When running from utils/, we need to look for .env in parent directory
import sys
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(env_path)

class AWSHandler:
    def __init__(self):
        self.aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
        self.aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        self.aws_region = os.getenv('AWS_REGION', 'us-east-1')
        self.bucket_name = os.getenv('S3_BUCKET_NAME')

        # Initialize S3 client
        try:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=self.aws_access_key,
                aws_secret_access_key=self.aws_secret_key,
                region_name=self.aws_region
            )
        except Exception as e:
            self.s3_client = None
            raise Exception(f"Failed to initialize AWS S3 client: {str(e)}")

    def test_connection(self):
        """Test AWS credentials and S3 bucket access"""
        try:
            # Test specific bucket access directly (doesn't require ListAllMyBuckets permission)
            self.s3_client.head_bucket(Bucket=self.bucket_name)

            return {
                'status': 'success',
                'message': f'Successfully connected to S3 bucket: {self.bucket_name}',
                'region': self.aws_region
            }
        except NoCredentialsError:
            return {
                'status': 'error',
                'message': 'AWS credentials not found. Check your .env file.',
                'error_type': 'credentials'
            }
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '403':
                return {
                    'status': 'error',
                    'message': f'Access denied to bucket {self.bucket_name}. Check IAM permissions.',
                    'error_type': 'permissions'
                }
            elif error_code == '404':
                return {
                    'status': 'error',
                    'message': f'Bucket {self.bucket_name} not found. Check bucket name.',
                    'error_type': 'bucket_not_found'
                }
            else:
                return {
                    'status': 'error',
                    'message': f'AWS error: {e.response["Error"]["Message"]}',
                    'error_type': 'aws_error'
                }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Unexpected error: {str(e)}',
                'error_type': 'unknown'
            }

    def upload_file(self, local_file_path, s3_key=None):
        """Upload a file to S3"""
        try:
            if not os.path.exists(local_file_path):
                raise FileNotFoundError(f"Local file not found: {local_file_path}")

            # Generate S3 key if not provided
            if s3_key is None:
                timestamp = datetime.now().strftime("%Y/%m/%d")
                filename = os.path.basename(local_file_path)
                s3_key = f"statements/{timestamp}/{filename}"

            # Upload the file
            self.s3_client.upload_file(local_file_path, self.bucket_name, s3_key)

            return {
                'status': 'success',
                'message': f'File uploaded successfully to S3',
                's3_key': s3_key,
                'bucket': self.bucket_name
            }

        except FileNotFoundError as e:
            return {
                'status': 'error',
                'message': str(e),
                'error_type': 'file_not_found'
            }
        except NoCredentialsError:
            return {
                'status': 'error',
                'message': 'AWS credentials not found',
                'error_type': 'credentials'
            }
        except ClientError as e:
            return {
                'status': 'error',
                'message': f'AWS S3 error: {e.response["Error"]["Message"]}',
                'error_type': 'aws_error'
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Upload failed: {str(e)}',
                'error_type': 'unknown'
            }

    def download_file(self, s3_key, local_file_path):
        """Download a file from S3"""
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(local_file_path), exist_ok=True)

            # Download the file
            self.s3_client.download_file(self.bucket_name, s3_key, local_file_path)

            return {
                'status': 'success',
                'message': f'File downloaded successfully from S3',
                'local_path': local_file_path
            }

        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                return {
                    'status': 'error',
                    'message': f'File not found in S3: {s3_key}',
                    'error_type': 'file_not_found'
                }
            else:
                return {
                    'status': 'error',
                    'message': f'AWS S3 error: {e.response["Error"]["Message"]}',
                    'error_type': 'aws_error'
                }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Download failed: {str(e)}',
                'error_type': 'unknown'
            }

    def delete_file(self, s3_key):
        """Delete a file from S3"""
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)

            return {
                'status': 'success',
                'message': f'File deleted successfully from S3: {s3_key}'
            }

        except ClientError as e:
            return {
                'status': 'error',
                'message': f'AWS S3 error: {e.response["Error"]["Message"]}',
                'error_type': 'aws_error'
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Delete failed: {str(e)}',
                'error_type': 'unknown'
            }

    def generate_presigned_url(self, s3_key, expiration=3600):
        """Generate a presigned URL for temporary access to a file"""
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': s3_key},
                ExpiresIn=expiration
            )

            return {
                'status': 'success',
                'message': f'Presigned URL generated successfully',
                'url': url,
                'expires_in': expiration
            }

        except ClientError as e:
            return {
                'status': 'error',
                'message': f'AWS S3 error: {e.response["Error"]["Message"]}',
                'error_type': 'aws_error'
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'URL generation failed: {str(e)}',
                'error_type': 'unknown'
            }


def test_aws_connection():
    """Standalone function to test AWS connection from command line"""
    print("Testing AWS S3 connection...")
    print(f"Looking for .env file at: {env_path}")
    print(f".env file exists: {os.path.exists(env_path)}")

    # Debug: Check if environment variables are loaded
    aws_key = os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret = os.getenv('AWS_SECRET_ACCESS_KEY')
    aws_region = os.getenv('AWS_REGION')
    bucket_name = os.getenv('S3_BUCKET_NAME')

    print(f"AWS_ACCESS_KEY_ID loaded: {'Yes' if aws_key else 'No'} ({'***' + aws_key[-4:] if aws_key else 'None'})")
    print(f"AWS_SECRET_ACCESS_KEY loaded: {'Yes' if aws_secret else 'No'}")
    print(f"AWS_REGION: {aws_region or 'Not set'}")
    print(f"S3_BUCKET_NAME: {bucket_name or 'Not set'}")
    print("-" * 50)

    try:
        handler = AWSHandler()
        result = handler.test_connection()

        print(f"Status: {result['status'].upper()}")
        print(f"Message: {result['message']}")

        if result['status'] == 'success':
            print(f"Region: {result['region']}")
            print("[SUCCESS] AWS S3 connection successful!")
        else:
            print(f"[ERROR] Connection failed: {result['error_type']}")

    except Exception as e:
        print(f"[ERROR] Failed to initialize AWS handler: {str(e)}")

    print("-" * 50)


# Allow running this file directly to test connection
if __name__ == "__main__":
    test_aws_connection()