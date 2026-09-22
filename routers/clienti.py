from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from database import supabase

router = APIRouter(prefix="/api/clienti", tags=["Clienti"])

@router.get("/")
def get_customers():
    try:
        all_customers = []
        batch_size = 1000
        start = 0
        
        while True:
            response = supabase.schema("gestionale_divise").table("clienti").select("*").range(start, start + batch_size - 1).execute()
            rows = response.data if response.data else []
            
            if not rows:
                break
                
            all_customers.extend(rows)
            
            if len(rows) < batch_size:
                break
                
            start += batch_size
            
        return all_customers
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{cliente_id}")
def get_cliente_dettaglio(cliente_id: int):
    try:
        resp = supabase.schema("gestionale_divise").table("clienti").select("*").eq("id", cliente_id).execute()
        if not resp.data:
            raise HTTPException(status_code=404, detail="Cliente non trovato nel sistema.")
        return resp.data[0]
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/")
def crea_cliente(payload_data: Dict[str, Any]):
    try:
        # Se non viene passato un campo azienda_id, lo impostiamo di default a 1
        if "azienda_id" not in payload_data:
            payload_data["azienda_id"] = 1

        resp = supabase.schema("gestionale_divise").table("clienti").insert(payload_data).execute()
        if not resp.data:
            raise HTTPException(status_code=500, detail="Errore durante la creazione del cliente.")
        
        return {
            "status": "success",
            "message": "Cliente creato con successo per il negozio fisico!",
            "cliente": resp.data[0]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{cliente_id}")
def aggiorna_cliente(cliente_id: int, payload_data: Dict[str, Any]):
    try:
        # Rimuoviamo l'id dal payload se presente per evitare conflitti nell'update
        payload_data.pop("id", None)

        resp = supabase.schema("gestionale_divise").table("clienti").update(payload_data).eq("id", cliente_id).execute()
        if not resp.data:
            raise HTTPException(status_code=404, detail="Cliente non trovato o errore durante l'aggiornamento.")
        
        return {
            "status": "success",
            "message": "Cliente aggiornato con successo!",
            "cliente": resp.data[0]
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
