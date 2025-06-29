"""
Google Gemini Configuration for Terminal Agent
"""

import os
from dotenv import load_dotenv

load_dotenv()

class GeminiConfig:
    """Gemini-specific configuration"""
    
    # Flask Configuration
    SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key-change-this-in-production')
    DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'
    
    # Server Configuration
    HOST = os.getenv('HOST', '0.0.0.0')
    PORT = int(os.getenv('PORT', 5000))
    
    # Google Gemini Configuration (FREE!)
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'your_gemini_api_key_here')
    GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-1.5-flash')
    
    # LangGraph Configuration
    RECURSION_LIMIT = int(os.getenv('RECURSION_LIMIT', 35))
    
    # PowerShell Configuration
    POWERSHELL_TIMEOUT = int(os.getenv('POWERSHELL_TIMEOUT', 30))
    
    # Security Configuration
    ENABLE_CORS = os.getenv('ENABLE_CORS', 'True').lower() == 'true'
    ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', '*').split(',')
    
    # UI Configuration
    TERMINAL_THEME = os.getenv('TERMINAL_THEME', 'dark')
    MAX_MESSAGE_LENGTH = int(os.getenv('MAX_MESSAGE_LENGTH', 1000))
    
    # Logging Configuration
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = os.getenv('LOG_FILE', 'terminal_agent.log')

def get_gemini_config():
    """Get Gemini configuration"""
    return GeminiConfig() 