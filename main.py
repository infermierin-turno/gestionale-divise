from fastapi import FastAPI, HTTPException
from database import supabase

app = FastAPI(title="Gestionale Divise API", version="1.0.0")

@app.get("/")
def read_root():
    return {"status": "online", "message": "Backend gestionale divisedivise.it attivo e operativo!"}

@app.get("/api/azienda/{azienda_id}")
def get_azienda_info(azienda_id: int):
    """Test rapido per verificare la lettura dal database Supabase nello schema dedicato"""
    try:
        response = supabase.table("aziende").select("*").eq("id", azienda_id).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Azienda non trovata")
        return {"azienda": response.data[0]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
