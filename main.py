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
        response = supabase.schema("gestionale_divise").table("articoli").select("*").execute()
        return response.data if response.data else []
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
        
        auth_response = requests.post(auth_url, json=auth_payload)
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

        sincronizzati = 0

        while url:
            response = requests.get(url, headers=headers)
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
                    pos = opt.get("position") # 1, 2, o 3
                    name = opt.get("name", "").strip().lower()
                    if pos:
                        option_map[pos] = name

                for variant in variants:
                    variant_id = variant.get("id")
                    sku = variant.get("sku") or f"SKU-{variant_id}"
                    price = float(variant.get("price", 0.0))
                    
                    val1 = variant.get("option1")
                    val2 = variant.get("option2")
                    val3 = variant.get("option3")

                    taglia = None
                    colore = None

                    # Associazione intelligente basata sul nome effettivo dell'opzione Shopify
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
                        # Se il campo si chiama manica o altro, lo gestiamo correttamente o lo ignoriamo se serve solo il colore

                    record = {
                        "azienda_id": azienda_id,
                        "shopify_product_id": product_id,
                        "shopify_variant_id": variant_id,
                        "sku": sku,
                        "nome": f"{product_title} - {variant.get('title', '')}".strip(" -"),
                        "taglia": taglia,
                        "colore": colore,
                        "prezzo": price,
                        "aliquota_iva": 22.00
                    }

                    if record["sku"]:
                        supabase.schema("gestionale_divise").table("articoli").upsert(record, on_conflict="sku").execute()
                    else:
                        supabase.schema("gestionale_divise").table("articoli").insert(record).execute()
                        
                    sincronizzati += 1

            # Gestione Link Header per la paginazione successiva
            link_header = response.headers.get("Link", "")
            url = None
            if 'rel="next"' in link_header:
                parts = link_header.split(",")
                for part in parts:
                    if 'rel="next"' in part:
                        url = part.split(";")[0].strip().strip("<>")

        return {
            "status": "success",
            "message": f"Sincronizzazione completata con successo! Totale articoli sincronizzati: {sincronizzati}",
            "total_synced": sincronizzati
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
