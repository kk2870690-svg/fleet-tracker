import pandas as pd
from database import supabase

# Read your CSV file from the folder
df = pd.read_csv("real_fleet.csv")

# Clean registration numbers
df["registration_number"] = df["registration_number"].astype(str).str.strip().str.upper()

# Convert to list of records
records = df.to_dict(orient="records")

# Push directly to Supabase
try:
    response = supabase.table("vehicles").upsert(records, on_conflict="registration_number").execute()
    print(f"✅ Success! Uploaded {len(response.data)} vehicles directly to Supabase.")
except Exception as e:
    print(f"❌ Error uploading: {e}")