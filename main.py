from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
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
        response = supabase.schema("gestionale_divise").table("aziende").select("*").eq("id", azienda_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Azienda non trovata nel sistema")
            
        return response.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/products")
def get_products():
    try:
        # Interroga la tabella 'articoli' nello schema personalizzato 'gestionale_divise'
        response = supabase.schema("gestionale_divise").table("articoli").select("*").execute()
        
        return response.data if response.data else []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/sync-shopify")
def sync_shopify_products(payload_data: Dict[str, Any]):
    try:
        articoli = payload_data.get("articoli", [])
        azienda_id = payload_data.get("azienda_id")

        if not articoli:
            return {"status": "success", "message": "Nessun articolo ricevuto.", "total_synced": 0}

        sincronizzati = 0
        for item in articoli:
            record = {
                "azienda_id": azienda_id,
                "shopify_product_id": item.get("shopify_product_id") or item.get("product_id"),
                "shopify_variant_id": item.get("shopify_variant_id") or item.get("variant_id"),
                "sku": item.get("sku", ""),
                "nome": item.get("nome") or item.get("title", "Senza nome"),
                "taglia": item.get("taglia") or item.get("option1"),
                "colore": item.get("colore") or item.get("option2"),
                "prezzo": float(item.get("prezzo") or item.get("price", 0.0)),
                "aliquota_iva": float(item.get("aliquota_iva", 22.00))
            }

            if record["sku"]:
                supabase.schema("gestionale_divise").table("articoli").upsert(record, on_conflict="sku").execute()
            else:
                supabase.schema("gestionale_divise").table("articoli").insert(record).execute()
                
            sincronizzati += 1

        return {
            "status": "success",
            "message": "Sincronizzazione completata con successo.",
            "total_synced": sincronizzati
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
