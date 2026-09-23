import os
import requests
import traceback
from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any
from database import supabase

router = APIRouter(prefix="/api/shopify", tags=["Shopify Orders"])

raw_shop_url = os.getenv("SHOP_URL") or os.getenv("SHOPIFY_SHOP", "")
SHOPIFY_SHOP = raw_shop_url.replace("https://", "").replace("http://", "").strip("/")
SHOPIFY_CLIENT_ID = os.getenv("SHOPIFY_CLIENT_ID")
SHOPIFY_CLIENT_SECRET = os.getenv("SHOPIFY_CLIENT_SECRET")
SHOPIFY_API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2024-01")

def get_shopify_access_token() -> str:
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
    
    return access_token

def process_and_save_order(ord_item: dict, azienda_id: int = 1):
    try:
        raw_id = ord_item.get("id")
        shopify_order_id = int(raw_id) if raw_id is not None else None
    except ValueError:
        shopify_order_id = raw_id

    shopify_order_name = ord_item.get("name", "")
    totale_ordine = float(ord_item.get("total_price", 0.0))
    
    totale_spedizione = 0.0
    shipping_lines = ord_item.get("shipping_lines", [])
    for line in shipping_lines:
        totale_spedizione += float(line.get("price", 0.0))
    
    totale_prodotti = round(totale_ordine - totale_spedizione, 2)
    
    financial_status = ord_item.get("financial_status", "pending")
    stato_ordine = "pagato" if financial_status == "paid" else "nuovo"

    # ==========================================
    # GESTIONE AUTOMATICA / ABBINAMENTO CLIENTE
    # ==========================================
    cliente_id = None
    customer_data = ord_item.get("customer")
    
    if customer_data:
        shopify_cust_id = customer_data.get("id")
        email = customer_data.get("email")
        nome = customer_data.get("first_name", "")
        cognome = customer_data.get("last_name", "")
        telefono = customer_data.get("phone", "")
        
        addresses = customer_data.get("addresses", [])
        default_address = next((addr for addr in addresses if addr.get("default")), addresses[0] if addresses else {})
        
        ragione_sociale = default_address.get("company", "")
        indirizzo_1 = default_address.get("address1", "")
        indirizzo_2 = default_address.get("address2", "")
        indirizzo_completo = f"{indirizzo_1} {indirizzo_2}".strip()
        citta = default_address.get("city", "")
        cap = default_address.get("zip", "")
        provincia = default_address.get("province_code", "")

        # 1. Cerchiamo se il cliente esiste già su Supabase tramite shopify_customer_id
        existing_cust = supabase.schema("gestionale_divise").table("clienti").select("id").eq("shopify_customer_id", shopify_cust_id).execute()
        
        if existing_cust.data:
            cliente_id = existing_cust.data[0].get("id")
        else:
            # 2. Se non esiste, lo creiamo al volo nella tabella clienti
            new_cust_payload = {
                "azienda_id": azienda_id,
                "shopify_customer_id": shopify_cust_id,
                "ragione_sociale": ragione_sociale if ragione_sociale else None,
                "nome": nome if nome else None,
                "cognome": cognome if cognome else None,
                "email": email if email else None,
                "telefono": telefono if telefono else None,
                "indirizzo": indirizzo_completo if indirizzo_completo else None,
                "citta": citta if citta else None,
                "cap": cap if cap else None,
                "provincia": provincia if provincia else None
            }
            ins_res = supabase.schema("gestionale_divise").table("clienti").insert(new_cust_payload).execute()
            if ins_res.data:
                cliente_id = ins_res.data[0].get("id")

    record = {
        "azienda_id": azienda_id,
        "shopify_order_id": shopify_order_id,
        "shopify_order_name": shopify_order_name,
        "canale_vendita": "Shopify",
        "cliente_id": cliente_id,
        "stato_ordine": stato_ordine,
        "totale_prodotti": totale_prodotti,
        "totale_spedizione": totale_spedizione,
        "totale_ordine": totale_ordine,
        "created_at": ord_item.get("created_at")
    }

    try:
        # Upsert della testata dell'ordine su Supabase
        res = supabase.schema("gestionale_divise").table("ordini").upsert(record, on_conflict="shopify_order_id").execute()
        
        # Recuperiamo l'ID interno dell'ordine appena inserito/aggiornato
        ordine_db_id = None
        if res.data and len(res.data) > 0:
            ordine_db_id = res.data[0].get("id")
        else:
            # Fallback di sicurezza: ricerchiamo l'ID tramite shopify_order_id
            sel_ord = supabase.schema("gestionale_divise").table("ordini").select("id").eq("shopify_order_id", shopify_order_id).execute()
            if sel_ord.data:
                ordine_db_id = sel_ord.data[0].get("id")

        # ==========================================
        # SALVATAGGIO RIGHE ORDINE (RIGHE_ORDINE)
        # ==========================================
        if ordine_db_id:
            # 1. Rimuoviamo eventuali vecchie righe per evitare duplicati in caso di aggiornamento ordine
            supabase.schema("gestionale_divise").table("righe_ordine").delete().eq("ordine_id", ordine_db_id).execute()

            line_items = ord_item.get("line_items", [])
            for item in line_items:
                variant_id = item.get("variant_id")
                product_id = item.get("product_id")
                sku = item.get("sku")
                qta = int(item.get("quantity", 1))
                prezzo_unitario = float(item.get("price", 0.0))
                totale_riga = round(qta * prezzo_unitario, 2)

                articolo_id = None

                # Cerchiamo l'articolo nel magazzino locale tramite shopify_variant_id
                if variant_id:
                    art_res = supabase.schema("gestionale_divise").table("articoli").select("id").eq("shopify_variant_id", variant_id).execute()
                    if art_res.data:
                        articolo_id = art_res.data[0].get("id")

                # Se non trovato per variant_id, proviamo con shopify_product_id
                if not articolo_id and product_id:
                    art_res = supabase.schema("gestionale_divise").table("articoli").select("id").eq("shopify_product_id", product_id).execute()
                    if art_res.data:
                        articolo_id = art_res.data[0].get("id")

                # Se non trovato per ID, proviamo tramite SKU
                if not articolo_id and sku:
                    art_res = supabase.schema("gestionale_divise").table("articoli").select("id").eq("sku", sku).execute()
                    if art_res.data:
                        articolo_id = art_res.data[0].get("id")

                # Inseriamo la riga nella tabella righe_ordine
                riga_payload = {
                    "ordine_id": ordine_db_id,
                    "articolo_id": articolo_id,  # Sarà associato se presente in magazzino, altrimenti null
                    "quantita": qta,
                    "prezzo_unitario": prezzo_unitario,
                    "totale_riga": totale_riga
                }
                supabase.schema("gestionale_divise").table("righe_ordine").insert(riga_payload).execute()

        return {"record": record, "response": str(res)}
    except Exception as db_err:
        print(f"ERRORE SUPABASE: {str(db_err)}")
        raise HTTPException(status_code=500, detail=f"Errore scrittura Supabase: {str(db_err)}")

@router.post("/sync-orders")
def sync_shopify_orders(payload_data: Dict[str, Any] = {}):
    try:
        azienda_id = payload_data.get("azienda_id", 1)
        access_token = get_shopify_access_token()

        url = f"https://{SHOPIFY_SHOP}/admin/api/{SHOPIFY_API_VERSION}/orders.json?status=any&limit=250"
        headers = {
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json"
        }

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
                process_and_save_order(ord_item, azienda_id)
                sincronizzati += 1

            link_header = response.headers.get("Link", "")
            url = None
            if 'rel="next"' in link_header:
                for part in link_header.split(","):
                    if 'rel="next"' in part:
                        url = part.split(";")[0].strip().strip("<>")

        return {
            "status": "success",
            "message": f"Sincronizzazione ordini, clienti e righe completata! Sincronizzati: {sincronizzati}",
            "total_synced": sincronizzati
        }
    except Exception as e:
        print(f"ERRORE SYNC: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/fetch-order-by-name")
def fetch_order_by_name(name: str = Query(...)):
    try:
        access_token = get_shopify_access_token()
        
        clean_name = name.strip()
        if clean_name.startswith("#"):
            clean_name = clean_name[1:]

        headers = {
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json"
        }

        orders = []
        url_1 = f"https://{SHOPIFY_SHOP}/admin/api/{SHOPIFY_API_VERSION}/orders.json?name={clean_name}&status=any"
        res_1 = requests.get(url_1, headers=headers, timeout=30)
        if res_1.status_code == 200:
            orders = res_1.json().get("orders", [])

        if not orders:
            url_2 = f"https://{SHOPIFY_SHOP}/admin/api/{SHOPIFY_API_VERSION}/orders.json?name=%23{clean_name}&status=any"
            res_2 = requests.get(url_2, headers=headers, timeout=30)
            if res_2.status_code == 200:
                orders = res_2.json().get("orders", [])

        if not orders:
            raise HTTPException(status_code=404, detail=f"Ordine '{name}' non trovato su Shopify.")

        result = process_and_save_order(orders[0])

        return {
            "status": "success",
            "message": f"Ordine {name} trovato e importato correttamente con righe e abbinamento cliente.",
            "data": result
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        print("ERRORE CRITICO FETCH:", traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/ordini")
def get_ordini_shopify():
    try:
        response = supabase.schema("gestionale_divise").table("ordini").select("*").order("created_at", desc=True).execute()
        return response.data if response.data else []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
