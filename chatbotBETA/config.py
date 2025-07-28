import os
import logging
from dotenv import load_dotenv # Required if this file needs to load env vars directly

load_dotenv()  

class Config:
    """Application configuration"""
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-YOUR_DEFAULT_API_KEY_IF_NEEDED")
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

    # Database Configuration
    DB_DRIVER = os.getenv("DB_DRIVER")
    DB_SERVER = os.getenv("DB_SERVER")
    DB_DATABASE = os.getenv("DB_DATABASE")
    DB_UID = os.getenv("DB_UID")
    DB_PWD = os.getenv("DB_PWD")

    @classmethod
    def get_connection_string(cls):
        """Construct the database connection string using environment variables."""
        print(f"DEBUG: Inside get_connection_string. cls.DB_SERVER: '{cls.DB_SERVER}'")
        try:
            # Access the attributes directly from the class
            server_val = cls.DB_SERVER
            database_val = cls.DB_DATABASE
            uid_val = cls.DB_UID
            pwd_val = cls.DB_PWD
            driver_val = cls.DB_DRIVER
            
            if any(param is None for param in [driver_val, server_val, database_val, uid_val, pwd_val]):
                 logging.error("Config:get_connection_string: One or more essential database environment variables (DB_DRIVER, DB_SERVER, DB_DATABASE, DB_UID, DB_PWD) are not set in the .env file.")
                 return None

            conn_str = (
                f"DRIVER={driver_val};"
                f"SERVER={server_val};"
                f"DATABASE={database_val};"
                f"UID={uid_val};"
                f"PWD={pwd_val};"
                r"Encrypt=no;TrustServerCertificate=no;"
            )
            return conn_str
        except Exception as e:
            logging.error(f"Config:get_connection_string: Error constructing database connection string: {e}")
        return None