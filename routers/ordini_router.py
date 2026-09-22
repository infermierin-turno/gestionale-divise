import os
import requests
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from database import supabase

router = APIRouter(prefix="/api/shopify", tags=["Shopify Orders"])

raw_shop_url = os.getenv("SHOP_URL") or os.getenv("SHOPIFY_SHOP", "")
SHOPIFY_SHOP = raw_shop_url.replace("https://", "").replace("http://", "").strip("/")
SHOPIFY_CLIENT_ID = os.getenv("SHOPIFY_CLIENT_ID")
SHOPIFY_CLIENT_SECRET = os.getenv("SHOPIFY_CLIENT_SECRET")
SHOPIFY_API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2024-01")

@router.post("/sync-orders")
def sync_shopify_orders(payload_data: Dict[str, Any] = {}):
    try:
        azienda_id = payload_data.get("azienda_id", 1)

        if not SHOPIFY_SHOP or not SHOPIFY_CLIENT_ID or not SHOPIFY_CLIENT_SECRET:
            raise HTTPException(status_code=500, detail="Credenziali Shopify mancanti nelle variabili d'ambiente.")

        auth_url = f"https://{SHOPIFY_SHOP}/admin/oauth/access_token"
        auth_payload = {
            "client_id": SHOPIFY_CLIENT_ID,
            "client_secret": SHOPIFY_CLIENT_SECRET,
            "grant_type": "client_credentials"
        }
        
        auth_response = requests.post(auth_url, json=auth_payload, timeout=30)
        if auth_response.status_code != 200:
            raise HTTPException(status_code=auth_response.status_code, detail=f"Autenticazione Shopify fallita: {auth_response.text}")

        access_token = auth_response.json().get("access_token")
        if not access_token:
            raise HTTPException(status_code=500, detail="Impossibile estrarre l'access_token di Shopify.")

        url = f"https://{SHOPIFY_SHOP}/admin/api/{SHOPIFY_API_VERSION}/orders.json?status=any&limit=250"
        headers = {
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json"
        }

        all_records = []
        sincronizzati = 0

        while url:
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=f"Errore chiamata ordini Shopify: {response.text}")
            
            data = response.json()
            orders = data.get("orders", [])

            if not orders:
                break

            for ord_item in orders:
                shopify_order_id = ord_item.get("id")
                shopify_order_name = ord_item.get("name", "")
                
                # Calcolo importi richiesti dalla tabella
                totale_ordine = float(ord_item.get("total_price", 0.0))
                
                # Spedizione
                totale_spedizione = 0.0
                shipping_lines = ord_item.get("shipping_lines", [])
                for line in shipping_lines:
                    totale_spedizione += float(line.get("price", 0.0))
                
                totale_prodotti = round(totale_ordine - totale_spedizione, 2)
                
                # Stato ordine mappato su stato_ordine
                financial_status = ord_item.get("financial_status", "pending")
                stato_ordine = "pagato" if financial_status == "paid" else "nuovo"

                record = {
                    "azienda_id": azienda_id,
                    "shopify_order_id": shopify_order_id,
                    "shopify_order_name": shopify_order_name,
                    "canale_vendita": "Shopify",
                    "stato_ordine": stato_ordine,
                    "totale_prodotti": totale_prodotti,
                    "totale_spedizione": totale_spedizione,
                    "totale_ordine": totale_ordine,
                    "created_at": ord_item.get("created_at")
                }

                all_records.append(record)

                if len(all_records) >= 1000:
                    dedup_dict = {r["shopify_order_id"]: r for r in all_records}
                    batch_dedup = list(dedup_dict.values())
                    supabase.schema("gestionale_divise").table("ordini").upsert(batch_dedup, on_conflict="shopify_order_id").execute()
                    sincronizzati += len(batch_dedup)
                    all_records = []

            link_header = response.headers.get("Link", "")
            url = None
            if 'rel="next"' in link_header:
                for part in link_header.split(","):
                    if 'rel="next"' in part:
                        url = part.split(";")[0].strip().strip("<>")

        if all_records:
            dedup_dict = {r["shopify_order_id"]: r for r in all_records}
            batch_dedup = list(dedup_dict.values())
            supabase.schema("gestionale_divise").table("ordini").upsert(batch_dedup, on_conflict="shopify_order_id").execute()
            sincronizzati += len(batch_dedup)

        return {
            "status": "success",
            "message": f"Sincronizzazione ordini completata! Sincronizzati: {sincronizzati}",
            "total_synced": sincronizzati
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/ordini")
def get_ordini_shopify():
    try:
        response = supabase.schema("gestionale_divise").table("ordini").select("*").order("created_at", desc=True).execute()
        return response.data if response.data else []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
