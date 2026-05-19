import os
from dotenv import load_dotenv
import json
load_dotenv()

class Config:
    DATABASE_URL = os.getenv("DATABASE_URL")
    SERVER_URL = os.getenv("SERVER_URL")