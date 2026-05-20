import os
from dotenv import load_dotenv
import json
load_dotenv()

class Config:
    DATABASE_URL = os.getenv("DATABASE_URL")
    SERVER_URL = os.getenv("SERVER_URL")
    PAYMOB_API_KEY = os.getenv("PAYMOB_API_KEY", "your_api_key_here")
    PAYMOB_INTEGRATION_ID = os.getenv("PAYMOB_INTEGRATION_ID", "your_integration_id_here")
    PAYMOB_IFRAME_ID = os.getenv("PAYMOB_IFRAME_ID", "your_iframe_id_here")
    PAYMOB_HMAC_SECRET = os.getenv("PAYMOB_HMAC_SECRET", "your_hmac_secret_here")