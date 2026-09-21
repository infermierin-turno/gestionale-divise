from fastapi import FastAPI, HTTPException
from database import supabase

app = FastAPI(
    title="Gestionale Divise API",
    description="Backend multi-canale per la gestione ordini e magazzino - divisedivise.it",
    version="1.0.0"
)

@app.get("/")
def read_root():
    return {
        "status": "online",
        "system": "Gestionale Divise API",
        "message": "Benvenuto nel backend FastAPI collegato a Supabase!"
    }

@app.get("/api/azienda/{azienda_id}")
def get_azienda(azienda_id: int):
    try:
        # Specifichiamo lo schema personalizzato 'gestionale_divise'
        response = supabase.schema("gestionale_divise").table("aziende").select("*").eq("id", azienda_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Azienda non trovata nel sistema")
            
        return response.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
