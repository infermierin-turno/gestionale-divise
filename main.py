import os
import requests
from fastapi import FastAPI, HTTPException
from typing import Dict, Any
from database import supabase

app = FastAPI(
    title="Gestionale Divise API",
    description="Backend multi-canale per la gestione ordini e magazzino - divisedivise.it",
    version="1.0.0"
)

# Lettura delle credenziali e pulizia automatica di eventuali prefissi http:// o https:// in SHOP_URL
raw_shop_url = os.getenv("SHOP_URL") or os.getenv("SHOPIFY_SHOP", "")
SHOPIFY_SHOP = raw_shop_url.replace("https://", "").replace("http://", "").strip("/")

SHOPIFY_CLIENT_ID = os.getenv("SHOPIFY_CLIENT_ID")
SHOPIFY_CLIENT_SECRET = os.getenv("SHOPIFY_CLIENT_SECRET")
SHOPIFY_API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2024-01")

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
        all_products = []
        batch_size = 1000
        start = 0
        
        # Ciclo di paginazione per superare il limite di 1000 righe per singola query imposto da Supabase
        while True:
            response = supabase.schema("gestionale_divise").table("articoli").select("*").range(start, start + batch_size - 1).execute()
            rows = response.data if response.data else []
            
            if not rows:
                break
                
            all_products.extend(rows)
            
            if len(rows) < batch_size:
                break
                
            start += batch_size
            
        return all_products
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/sync-shopify")
def sync_shopify_products(payload_data: Dict[str, Any]):
    try:
        azienda_id = payload_data.get("azienda_id", 1)

        if not SHOPIFY_SHOP or not SHOPIFY_CLIENT_ID or not SHOPIFY_CLIENT_SECRET:
            raise HTTPException(status_code=500, detail="Credenziali Shopify (SHOP_URL, Client ID o Client Secret) mancanti nelle variabili d'ambiente di Render.")

        # 1. Ottenimento del token di accesso tramite Client Credentials / Custom App Auth
        auth_url = f"https://{SHOPIFY_SHOP}/admin/oauth/access_token"
        auth_payload = {
            "client_id": SHOPIFY_CLIENT_ID,
            "client_secret": SHOPIFY_CLIENT_SECRET,
            "grant_type": "client_credentials"
        }
        
        auth_response = requests.post(auth_url, json=auth_payload, timeout=30)
        if auth_response.status_code != 200:
            raise HTTPException(status_code=auth_response.status_code, detail=f"Autenticazione Shopify fallita: {auth_response.text}")

        token_data = auth_response.json()
        access_token = token_data.get("access_token")

        if not access_token:
            raise HTTPException(status_code=500, detail="Impossibile estrarre l'access_token dalla risposta di Shopify.")

        # 2. Interrogazione dei prodotti con paginazione
        url = f"https://{SHOPIFY_SHOP}/admin/api/{SHOPIFY_API_VERSION}/products.json?limit=250"
        headers = {
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json"
        }

        all_records = []
        active_variant_ids = []
        sincronizzati = 0

        while url:
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=f"Errore chiamata prodotti Shopify: {response.text}")
            
            data = response.json()
            products = data.get("products", [])

            if not products:
                break

            for item in products:
                product_id = item.get("id")
                product_title = item.get("title", "Senza nome")
                variants = item.get("variants", [])
                options = item.get("options", [])

                # Mappatura dinamica delle opzioni in base al nome (es. Taglia, Colore, Manica)
                option_map = {}
                for opt in options:
                    pos = opt.get("position")
                    name = opt.get("name", "").strip().lower()
                    if pos:
                        option_map[pos] = name

                for variant in variants:
                    variant_id = variant.get("id")
                    active_variant_ids.append(variant_id)

                    sku = variant.get("sku") or f"SKU-{variant_id}"
                    price = float(variant.get("price", 0.0))
                    
                    val1 = variant.get("option1")
                    val2 = variant.get("option2")
                    val3 = variant.get("option3")

                    taglia = None
                    colore = None
                    dettaglio_extra = []

                    opt_names = [option_map.get(1, ""), option_map.get(2, ""), option_map.get(3, "")]
                    opt_vals = [val1, val2, val3]

                    for name, val in zip(opt_names, opt_vals):
                        if not val or val == "Default Title":
                            continue
                        
                        name_lower = name.lower()
                        if any(k in name_lower for k in ["taglia", "size", "dimensione"]):
                            taglia = val
                        elif any(k in name_lower for k in ["colore", "color"]):
                            colore = val
                        else:
                            dettaglio_extra.append(val)

                    # Componiamo il nome descrittivo della variante includendo eventuali opzioni extra (es. Manica Lunga/Corta)
                    suffix_extra = " / ".join(dettaglio_extra)
                    if variant.get('title') and variant.get('title') != "Default Title":
                        variant_title_part = variant.get('title')
                    else:
                        variant_title_part = " - ".join([v for v in [taglia, colore, suffix_extra] if v])

                    record = {
                        "azienda_id": azienda_id,
                        "shopify_product_id": product_id,
                        "shopify_variant_id": variant_id,
                        "sku": sku,
                        "nome": f"{product_title} - {variant_title_part}".strip(" -"),
                        "taglia": taglia,
                        "colore": colore,
                        "prezzo": price,
                        "aliquota_iva": 22.00
                    }

                    all_records.append(record)

                    # Invio in batch da 1000 elementi basato su shopify_variant_id come chiave univoca
                    if len(all_records) >= 1000:
                        dedup_dict = {r["shopify_variant_id"]: r for r in all_records}
                        batch_dedup = list(dedup_dict.values())

                        supabase.schema("gestionale_divise").table("articoli").upsert(batch_dedup, on_conflict="shopify_variant_id").execute()
                        sincronizzati += len(batch_dedup)
                        all_records = []

            # Gestione Link Header per la paginazione successiva di Shopify
            link_header = response.headers.get("Link", "")
            url = None
            if 'rel="next"' in link_header:
                parts = link_header.split(",")
                for part in parts:
                    if 'rel="next"' in part:
                        url = part.split(";")[0].strip().strip("<>")

        # Invio degli eventuali record rimanenti inferiori a 1000
        if all_records:
            dedup_dict = {r["shopify_variant_id"]: r for r in all_records}
            batch_dedup = list(dedup_dict.values())

            supabase.schema("gestionale_divise").table("articoli").upsert(batch_dedup, on_conflict="shopify_variant_id").execute()
            sincronizzati += len(batch_dedup)

        # 3. Pulizia automatica sicura a blocchi (evita il limite URL too long)
        deleted_count = 0
        if active_variant_ids:
            db_variants_resp = supabase.schema("gestionale_divise").table("articoli").select("shopify_variant_id").eq("azienda_id", azienda_id).execute()
            db_variant_ids = [row["shopify_variant_id"] for row in db_variants_resp.data] if db_variants_resp.data else []
            
            ids_to_delete = [vid for vid in db_variant_ids if vid not in active_variant_ids]
            
            if ids_to_delete:
                chunk_size = 200
                for i in range(0, len(ids_to_delete), chunk_size):
                    chunk_del = ids_to_delete[i:i + chunk_size]
                    del_resp = supabase.schema("gestionale_divise").table("articoli").delete().in_("shopify_variant_id", chunk_del).execute()
                    if del_resp.data:
                        deleted_count += len(del_resp.data)

        return {
            "status": "success",
            "message": f"Sincronizzazione completata! Aggiornati/Inseriti: {sincronizzati}, Rimossi dal DB: {deleted_count}",
            "total_synced": sincronizzati,
            "total_deleted": deleted_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
