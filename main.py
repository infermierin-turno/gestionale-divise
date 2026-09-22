import os
import requests
from fastapi import FastAPI, HTTPException
from typing import Dict, Any
from database import supabase
from routers import clienti, ordini_router

app = FastAPI(
    title="Gestionale Divise API",
    description="Backend multi-canale per la gestione ordini, magazzino e clienti - divisedivise.it",
    version="1.2.4"
)

# Inclusione dei router
app.include_router(clienti.router)
app.include_router(ordini_router.router)

# Lettura credenziali Shopify globali
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
        "message": "Backend FastAPI operativo con Supabase!"
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

# ==========================================
# GESTIONE DOCUMENTI E RIGHE
# ==========================================
@app.get("/api/documenti")
def get_documenti():
    try:
        all_docs = []
        batch_size = 1000
        start = 0
        while True:
            response = supabase.schema("gestionale_divise").table("documenti").select("*").range(start, start + batch_size - 1).execute()
            rows = response.data if response.data else []
            if not rows:
                break
            all_docs.extend(rows)
            if len(rows) < batch_size:
                break
            start += batch_size
        return all_docs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/documenti/{documento_id}")
def get_documento_dettaglio(documento_id: int):
    try:
        doc_resp = supabase.schema("gestionale_divise").table("documenti").select("*").eq("id", documento_id).execute()
        if not doc_resp.data:
            raise HTTPException(status_code=404, detail="Documento non trovato nel sistema.")
        documento = doc_resp.data[0]
        
        righe_resp = supabase.schema("gestionale_divise").table("documenti_righe").select("*").eq("documento_id", documento_id).execute()
        righe = righe_resp.data if righe_resp.data else []
        for riga in righe:
            articolo_id = riga.get("articolo_id")
            articolo_data = None
            if articolo_id:
                art_resp = supabase.schema("gestionale_divise").table("articoli").select("*").eq("id", articolo_id).execute()
                if art_resp.data:
                    articolo_data = art_resp.data[0]
            riga["articolo"] = articolo_data
        documento["righe"] = righe
        
        cliente_id = documento.get("cliente_id")
        cliente_data = None
        if cliente_id:
            cli_resp = supabase.schema("gestionale_divise").table("clienti").select("*").eq("id", cliente_id).execute()
            if cli_resp.data:
                cliente_data = cli_resp.data[0]
        documento["cliente"] = cliente_data
        return documento
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/documenti")
def crea_documento(payload_data: Dict[str, Any]):
    try:
        testata = payload_data.get("testata", {})
        righe = payload_data.get("righe", [])
        if not testata:
            raise HTTPException(status_code=400, detail="Dati di testata mancanti.")

        doc_resp = supabase.schema("gestionale_divise").table("documenti").insert(testata).execute()
        if not doc_resp.data:
            raise HTTPException(status_code=500, detail="Errore creazione documento.")
        nuovo_documento = doc_resp.data[0]
        documento_id = nuovo_documento.get("id")

        righe_inserite = []
        if righe and documento_id:
            for riga in righe:
                riga["documento_id"] = documento_id
            righe_resp = supabase.schema("gestionale_divise").table("documenti_righe").insert(righe).execute()
            righe_inserite = righe_resp.data if righe_resp.data else []

        nuovo_documento["righe"] = righe_inserite
        return {"status": "success", "documento": nuovo_documento}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# GESTIONE MAGAZZINO
# ==========================================
@app.post("/api/magazzino/carico-deposito")
def carico_deposito(payload_data: Dict[str, Any]):
    try:
        articolo_id = payload_data.get("articolo_id")
        quantita = int(payload_data.get("quantita", 0))
        if not articolo_id or quantita <= 0:
            raise HTTPException(status_code=400, detail="Dati non validi.")
        resp = supabase.schema("gestionale_divise").table("articoli").select("giacenza_deposito").eq("id", articolo_id).execute()
        if not resp.data:
            raise HTTPException(status_code=404, detail="Articolo non trovato.")
        deposito_attuale = int(resp.data[0].get("giacenza_deposito", 0))
        nuovo_deposito = deposito_attuale + quantita
        supabase.schema("gestionale_divise").table("articoli").update({"giacenza_deposito": nuovo_deposito}).eq("id", articolo_id).execute()
        return {"status": "success", "giacenza_deposito": nuovo_deposito}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/magazzino/trasferisci")
def trasferisci_giacenza(payload_data: Dict[str, Any]):
    try:
        articolo_id = payload_data.get("articolo_id")
        quantita = int(payload_data.get("quantita", 0))
        direzione = payload_data.get("direzione")
        if not articolo_id or quantita <= 0 or direzione not in ["dep_to_neg", "neg_to_dep"]:
            raise HTTPException(status_code=400, detail="Parametri non validi.")
        resp = supabase.schema("gestionale_divise").table("articoli").select("giacenza_deposito, giacenza_negozio").eq("id", articolo_id).execute()
        if not resp.data:
            raise HTTPException(status_code=404, detail="Articolo non trovato.")
        articolo = resp.data[0]
        dep_c = int(articolo.get("giacenza_deposito", 0))
        neg_c = int(articolo.get("giacenza_negozio", 0))
        if direzione == "dep_to_neg":
            if dep_c < quantita:
                raise HTTPException(status_code=400, detail="Giacenza insufficiente in Deposito.")
            nuovo_dep, nuovo_neg = dep_c - quantita, neg_c + quantita
        else:
            if neg_c < quantita:
                raise HTTPException(status_code=400, detail="Giacenza insufficiente in Negozio.")
            nuovo_dep, nuovo_neg = dep_c + quantita, neg_c - quantita
        supabase.schema("gestionale_divise").table("articoli").update({"giacenza_deposito": nuovo_dep, "giacenza_negozio": nuovo_neg}).eq("id", articolo_id).execute()
        return {"status": "success", "giacenza_deposito": nuovo_dep, "giacenza_negozio": nuovo_neg}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# SINCRONIZZAZIONE SHOPIFY (PRODOTTI / CLIENTI)
# ==========================================
@app.post("/api/sync-shopify-customers")
def sync_shopify_customers(payload_data: Dict[str, Any] = {}):
    try:
        azienda_id = payload_data.get("azienda_id", 1)
        if not SHOPIFY_SHOP or not SHOPIFY_CLIENT_ID or not SHOPIFY_CLIENT_SECRET:
            raise HTTPException(status_code=500, detail="Credenziali Shopify mancanti.")
        auth_resp = requests.post(f"https://{SHOPIFY_SHOP}/admin/oauth/access_token", json={"client_id": SHOPIFY_CLIENT_ID, "client_secret": SHOPIFY_CLIENT_SECRET, "grant_type": "client_credentials"}, timeout=30)
        access_token = auth_resp.json().get("access_token")
        
        url = f"https://{SHOPIFY_SHOP}/admin/api/{SHOPIFY_API_VERSION}/customers.json?limit=250"
        headers = {"X-Shopify-Access-Token": access_token, "Content-Type": "application/json"}
        all_records, sincronizzati = [], 0
        while url:
            resp = requests.get(url, headers=headers, timeout=30)
            data = resp.json()
            customers = data.get("customers", [])
            if not customers: break
            for cust in customers:
                addr = next((a for a in cust.get("addresses", []) if a.get("default")), cust.get("addresses", [{}])[0])
                all_records.append({
                    "azienda_id": azienda_id,
                    "shopify_customer_id": cust.get("id"),
                    "ragione_sociale": addr.get("company") or None,
                    "nome": cust.get("first_name") or None,
                    "cognome": cust.get("last_name") or None,
                    "email": cust.get("email") or None,
                    "telefono": cust.get("phone") or None,
                    "indirizzo": f"{addr.get('address1', '')} {addr.get('address2', '')}".strip() or None,
                    "citta": addr.get("city") or None,
                    "cap": addr.get("zip") or None,
                    "provincia": addr.get("province_code") or None
                })
            link = resp.headers.get("Link", "")
            url = next((p.split(";")[0].strip().strip("<>") for p in link.split(",") if 'rel="next"' in p), None)
        if all_records:
            dedup = list({r["shopify_customer_id"]: r for r in all_records}.values())
            supabase.schema("gestionale_divise").table("clienti").upsert(dedup, on_conflict="shopify_customer_id").execute()
            sincronizzati = len(dedup)
        return {"status": "success", "total_synced": sincronizzati}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/sync-shopify")
def sync_shopify_products(payload_data: Dict[str, Any] = {}):
    try:
        azienda_id = payload_data.get("azienda_id", 1)
        if not SHOPIFY_SHOP or not SHOPIFY_CLIENT_ID or not SHOPIFY_CLIENT_SECRET:
            raise HTTPException(status_code=500, detail="Credenziali Shopify mancanti.")
        auth_resp = requests.post(f"https://{SHOPIFY_SHOP}/admin/oauth/access_token", json={"client_id": SHOPIFY_CLIENT_ID, "client_secret": SHOPIFY_CLIENT_SECRET, "grant_type": "client_credentials"}, timeout=30)
        access_token = auth_resp.json().get("access_token")
        
        url = f"https://{SHOPIFY_SHOP}/admin/api/{SHOPIFY_API_VERSION}/products.json?limit=250"
        headers = {"X-Shopify-Access-Token": access_token, "Content-Type": "application/json"}
        all_records, active_variants, sincronizzati = [], [], 0
        while url:
            resp = requests.get(url, headers=headers, timeout=30)
            data = resp.json()
            products = data.get("products", [])
            if not products: break
            for item in products:
                opt_map = {o.get("position"): o.get("name", "").lower() for o in item.get("options", [])}
                for var in item.get("variants", []):
                    vid = var.get("id")
                    active_variants.append(vid)
                    v1 = var.get("option1")
                    taglia = v1 if "taglia" in opt_map.get(1, "") or "size" in opt_map.get(1, "") else None
                    colore = v1 if "colore" in opt_map.get(1, "") or "color" in opt_map.get(1, "") else None
                    all_records.append({
                        "azienda_id": azienda_id,
                        "shopify_product_id": item.get("id"),
                        "shopify_variant_id": vid,
                        "sku": var.get("sku") or f"SKU-{vid}",
                        "nome": f"{item.get('title')} - {var.get('title')}".strip(),
                        "taglia": taglia,
                        "colore": colore,
                        "prezzo": float(var.get("price", 0.0)),
                        "aliquota_iva": 22.00
                    })
            link = resp.headers.get("Link", "")
            url = next((p.split(";")[0].strip().strip("<>") for p in link.split(",") if 'rel="next"' in p), None)
        if all_records:
            dedup = list({r["shopify_variant_id"]: r for r in all_records}.values())
            supabase.schema("gestionale_divise").table("articoli").upsert(dedup, on_conflict="shopify_variant_id").execute()
            sincronizzati = len(dedup)
        return {"status": "success", "total_synced": sincronizzati}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
