import os
from dotenv import load_dotenv
from supabase import create_client, Client

# Load variables from .env file
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://czzcfxnswocjpedolbhe.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN6emNmeG5zd29janBlZG9sYmhlIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODkyMDg4NjAsImV4cCI6MjEwNDc4NDg2MH0.gJOuWaeqvIbkeZ2zPJjpBZWJgYqLA-_RZKvi9EFsVps")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing Supabase credentials in .env file or fallback configuration.")

# Initialize the Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)