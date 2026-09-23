from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import traceback
from database import supabase

router = APIRouter(prefix="/api", tags=["Dipendenti API"])

@router.post("/dipendenti")
def crea_dipendente(payload: Dict[str, Any]):
    try:
        azienda_id = payload.get("azienda_id", 1)
        nome = payload.get("nome")
        cognome = payload.get("cognome")
        email = payload.get("email")
        password_hash = payload.get("password_hash")
        ruolo = payload.get("ruolo", "operatore")
        attivo = payload.get("attivo", True)

        if not email or not password_hash or not nome or not cognome:
            raise HTTPException(status_code=400, detail="Tutti i campi obbligatori sono richiesti.")

        dipendente_payload = {
            "azienda_id": int(azienda_id) if azienda_id else 1,
            "nome": nome,
            "cognome": cognome,
            "email": email,
            "password_hash": password_hash,
            "ruolo": ruolo,
            "attivo": attivo
        }

        res = supabase.schema("gestionale_divise").table("dipendenti").insert(dipendente_payload).execute()
        
        if not res.data:
            raise HTTPException(status_code=500, detail="Errore inserimento dipendente su Supabase.")

        return {
            "status": "success",
            "message": "Dipendente creato con successo!",
            "data": res.data[0]
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        print("ERRORE CREAZIONE DIPENDENTE:", traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/dipendenti")
def get_dipendenti():
    try:
        res = supabase.schema("gestionale_divise").table("dipendenti").select("*").order("id", desc=True).execute()
        return res.data if res.data else []
    except Exception as e:
        print("ERRORE GET DIPENDENTI:", traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/dipendenti/{dipendente_id}")
def aggiorna_dipendente(dipendente_id: int, payload: Dict[str, Any]):
    try:
        azienda_id = payload.get("azienda_id", 1)
        nome = payload.get("nome")
        cognome = payload.get("cognome")
        email = payload.get("email")
        password_hash = payload.get("password_hash")
        ruolo = payload.get("ruolo", "operatore")
        attivo = payload.get("attivo", True)

        if not email or not password_hash or not nome or not cognome:
            raise HTTPException(status_code=400, detail="Tutti i campi obbligatori sono richiesti.")

        dipendente_payload = {
            "azienda_id": int(azienda_id) if azienda_id else 1,
            "nome": nome,
            "cognome": cognome,
            "email": email,
            "password_hash": password_hash,
            "ruolo": ruolo,
            "attivo": attivo
        }

        res = supabase.schema("gestionale_divise").table("dipendenti").update(dipendente_payload).eq("id", dipendente_id).execute()

        if not res.data:
            raise HTTPException(status_code=404, detail="Dipendente non trovato o errore durante l'aggiornamento.")

        return {
            "status": "success",
            "message": "Dipendente aggiornato con successo!",
            "data": res.data[0]
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        print("ERRORE AGGIORNAMENTO DIPENDENTE:", traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
