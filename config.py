"""Application configuration module."""
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Flask application configuration loaded from environment variables with sensible defaults."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret'
    DATABASE = os.environ.get('DATABASE') or os.path.join(BASE_DIR, 'instance', 'database.db')
    # Company details for invoices and headers
    COMPANY_NAME = os.environ.get('COMPANY_NAME') or 'Sari-Sari Store'
    COMPANY_ADDRESS = os.environ.get('COMPANY_ADDRESS') or '123 Business Road, City, Philippines'
    COMPANY_EMAIL = os.environ.get('COMPANY_EMAIL') or 'info@example.com'
    COMPANY_PHONE = os.environ.get('COMPANY_PHONE') or '+63 912 345 6789'
    COMPANY_TIN = os.environ.get('COMPANY_TIN') or 'TIN: 000-000-000'
