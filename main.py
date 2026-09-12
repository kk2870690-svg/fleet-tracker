import io
from datetime import date, datetime
import pandas as pd
from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from database import supabase
from typing import Optional

app = FastAPI(
    title="FleetPulse - Commercial Fleet Compliance API",
    description="Backend API to manage commercial taxi compliance, statutory expiries, and fleet operations.",
    version="1.0.0"
)

# Enable CORS so your web page / dashboard can communicate with FastAPI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Data Models ---
class VehicleCreate(BaseModel):
    registration_number: str = Field(..., example="UP85-AX-1011")
    vehicle_type: str = Field(..., example="7-Seater")
    make: str = Field(..., example="Maruti")
    model: str = Field(..., example="Ertiga")
    registration_year: int = Field(..., example=2021)
    tax_expiry_date: date = Field(..., example="2027-03-31")
    insurance_expiry_date: date = Field(..., example="2026-09-20")
    pucc_expiry_date: date = Field(..., example="2026-09-07")
    permit_expiry_date: date = Field(..., example="2026-12-15")
    fitness_expiry_date: Optional[date] = None

# --- Helper Function for Expiry Calculation ---
def calculate_status(target_date: date, today: date):
    days_left = (target_date - today).days
    if days_left < 0:
        return {"days_left": days_left, "status": "EXPIRED"}
    elif days_left <= 30:
        return {"days_left": days_left, "status": "EXPIRING_SOON"}
    return {"days_left": days_left, "status": "VALID"}


# --- Routes ---

@app.get("/")
def health_check():
    return {"status": "online", "service": "FleetPulse API"}


@app.get("/vehicles")
def get_all_vehicles():
    """Returns all fleet vehicles with live calculated age and status badges."""
    res = supabase.table("vehicles").select("*").order("created_at", desc=True).execute()
    today = date.today()
    current_year = today.year
    
    fleet_data = []
    for car in res.data:
        age = current_year - car["registration_year"]
        
        tax_d = datetime.strptime(car["tax_expiry_date"], "%Y-%m-%d").date()
        ins_d = datetime.strptime(car["insurance_expiry_date"], "%Y-%m-%d").date()
        puc_d = datetime.strptime(car["pucc_expiry_date"], "%Y-%m-%d").date()
        per_d = datetime.strptime(car["permit_expiry_date"], "%Y-%m-%d").date()
        
        fleet_data.append({
            "id": car["id"],
            "registration_number": car["registration_number"],
            "vehicle_type": car["vehicle_type"],
            "make": car["make"],
            "model": car["model"],
            "registration_year": car["registration_year"],
            "vehicle_age": f"{age} years old" if age > 0 else "Brand new (< 1 year)",
            "compliance": {
                "tax": {"expiry": car["tax_expiry_date"], **calculate_status(tax_d, today)},
                "insurance": {"expiry": car["insurance_expiry_date"], **calculate_status(ins_d, today)},
                "pucc": {"expiry": car["pucc_expiry_date"], **calculate_status(puc_d, today)},
                "permit": {"expiry": car["permit_expiry_date"], **calculate_status(per_d, today)}
            }
        })
        
    return {"total_count": len(fleet_data), "vehicles": fleet_data}


@app.post("/vehicles", status_code=201)
def add_single_vehicle(payload: VehicleCreate):
    """Register a single vehicle manually."""
    record = payload.model_dump(mode="json")
    record["registration_number"] = record["registration_number"].strip().upper()
    
    res = supabase.table("vehicles").upsert(record, on_conflict="registration_number").execute()
    if not res.data:
        raise HTTPException(status_code=400, detail="Failed to register vehicle in Supabase.")
    return {"message": "Vehicle registered successfully", "data": res.data[0]}


@app.post("/vehicles/bulk-upload")
async def bulk_upload_vehicles(file: UploadFile = File(...)):
    """Upload fleet data in bulk via CSV or Excel (.xlsx)."""
    contents = await file.read()
    
    try:
        if file.filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(contents))
        elif file.filename.endswith((".xls", ".xlsx")):
            df = pd.read_excel(io.BytesIO(contents))
        else:
            raise HTTPException(status_code=400, detail="Only .csv and .xlsx files are supported.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")

    required_cols = [
        "registration_number", "vehicle_type", "make", "model",
        "registration_year", "tax_expiry_date", "insurance_expiry_date",
        "pucc_expiry_date", "permit_expiry_date"
    ]
    
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise HTTPException(status_code=422, detail=f"Missing required columns: {missing}")

    # Standardize dates into YYYY-MM-DD
    date_cols = ["tax_expiry_date", "insurance_expiry_date", "pucc_expiry_date", "permit_expiry_date"]
    for col in date_cols:
        df[col] = pd.to_datetime(df[col], errors="coerce").dt.strftime("%Y-%m-%d")

    if df[date_cols].isna().any().any():
        raise HTTPException(status_code=422, detail="One or more rows contain invalid dates. Ensure format is YYYY-MM-DD.")

    df["registration_number"] = df["registration_number"].astype(str).str.strip().str.upper()
    records = df.to_dict(orient="records")

    res = supabase.table("vehicles").upsert(records, on_conflict="registration_number").execute()
    return {"message": "Bulk import completed successfully", "imported_count": len(res.data)}


@app.get("/alerts/expiring-soon")
def get_alerts(threshold_days: int = Query(default=30, ge=1, le=180)):
    """Returns a flat list of expired documents or documents expiring within the threshold."""
    res = supabase.table("vehicles").select("*").execute()
    today = date.today()
    alerts = []
    
    for car in res.data:
        doc_map = {
            "Road Tax": car["tax_expiry_date"],
            "Insurance Policy": car["insurance_expiry_date"],
            "PUCC Certificate": car["pucc_expiry_date"],
            "Commercial Permit": car["permit_expiry_date"]
        }
        
        for doc_name, exp_str in doc_map.items():
            exp_d = datetime.strptime(exp_str, "%Y-%m-%d").date()
            days_left = (exp_d - today).days
            
            if days_left <= threshold_days:
                alerts.append({
                    "registration_number": car["registration_number"],
                    "vehicle": f"{car['make']} {car['model']}",
                    "document": doc_name,
                    "expiry_date": exp_str,
                    "days_remaining": days_left,
                    "severity": "CRITICAL_EXPIRED" if days_left < 0 else "WARNING_DUE_SOON"
                })
                
    return {"total_alerts": len(alerts), "alerts": alerts}


@app.get("/fleet/summary")
def get_fleet_summary():
    """High-level summary metrics for executive dashboard."""
    res = supabase.table("vehicles").select("*").execute()
    today = date.today()
    
    total = len(res.data)
    grounded = 0
    due_soon = 0
    compliant = 0

    for car in res.data:
        dates = [
            datetime.strptime(car["tax_expiry_date"], "%Y-%m-%d").date(),
            datetime.strptime(car["insurance_expiry_date"], "%Y-%m-%d").date(),
            datetime.strptime(car["pucc_expiry_date"], "%Y-%m-%d").date(),
            datetime.strptime(car["permit_expiry_date"], "%Y-%m-%d").date(),
        ]
        min_days = min((d - today).days for d in dates)
        
        if min_days < 0:
            grounded += 1
        elif min_days <= 30:
            due_soon += 1
        else:
            compliant += 1

    return {
        "fleet_size": total,
        "grounded_vehicles": grounded,
        "due_within_30_days": due_soon,
        "fully_compliant": compliant,
        "compliance_rate": f"{(compliant / total * 100):.1f}%" if total else "0.0%"
    }