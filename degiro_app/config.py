import os
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'
    DEBUG = os.environ.get('DEBUG', 'False').lower() in ('true', '1', 't')

    # Add other configuration variables here
