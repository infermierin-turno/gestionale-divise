import os
import requests
from fastapi import FastAPI, HTTPException
from typing import Dict, Any
from database import supabase

app = FastAPI(
    title="Gestionale Divise API",
    description="Backend multi-canale per la gestione ordini, magazzino e clienti - divisedivise.it",
    version="1.1.0"
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

@app.get("/api/customers")
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

@app.get("/api/clienti/{cliente_id}")
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
        
        # Recupero righe documento
        righe_resp = supabase.schema("gestionale_divise").table("documenti_righe").select("*").eq("documento_id", documento_id).execute()
        documento["righe"] = righe_resp.data if righe_resp.data else []
        
        # Recupero automatico dei dati del cliente associato (JOIN logico)
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
            raise HTTPException(status_code=400, detail="Dati di testata del documento mancanti.")

        doc_resp = supabase.schema("gestionale_divise").table("documenti").insert(testata).execute()
        if not doc_resp.data:
            raise HTTPException(status_code=500, detail="Errore durante la creazione del documento.")
        
        nuovo_documento = doc_resp.data[0]
        documento_id = nuovo_documento.get("id")

        righe_inserite = []
        if righe and documento_id:
            for riga in righe:
                riga["documento_id"] = documento_id
            
            righe_resp = supabase.schema("gestionale_divise").table("documenti_righe").insert(righe).execute()
            righe_inserite = righe_resp.data if righe_resp.data else []

        nuovo_documento["righe"] = righe_inserite

        return {
            "status": "success",
            "message": "Documento creato con successo!",
            "documento": nuovo_documento
        }
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
            raise HTTPException(status_code=400, detail="ID articolo mancante o quantità di carico non valida.")

        resp = supabase.schema("gestionale_divise").table("articoli").select("giacenza_deposito").eq("id", articolo_id).execute()
        
        if not resp.data:
            raise HTTPException(status_code=404, detail="Articolo non trovato nel database.")

        deposito_attuale = int(resp.data[0].get("giacenza_deposito", 0))
        nuovo_deposito = deposito_attuale + quantita

        supabase.schema("gestionale_divise").table("articoli").update({
            "giacenza_deposito": nuovo_deposito
        }).eq("id", articolo_id).execute()

        return {
            "status": "success",
            "message": "Carico in deposito completato con successo!",
            "giacenza_deposito": nuovo_deposito
        }

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

        if not articolo_id or quantita <= 0:
            raise HTTPException(status_code=400, detail="ID articolo mancante o quantità non valida.")

        if direzione not in ["dep_to_neg", "neg_to_dep"]:
            raise HTTPException(status_code=400, detail="Direzione di trasferimento non valida.")

        resp = supabase.schema("gestionale_divise").table("articoli").select("giacenza_deposito, giacenza_negozio").eq("id", articolo_id).execute()
        
        if not resp.data:
            raise HTTPException(status_code=404, detail="Articolo non trovato nel database.")

        articolo = resp.data[0]
        deposito_attuale = int(articolo.get("giacenza_deposito", 0))
        negozio_attuale = int(articolo.get("giacenza_negozio", 0))

        if direzione == "dep_to_neg":
            if deposito_attuale < quantita:
                raise HTTPException(status_code=400, detail=f"Giacenza insufficiente in Deposito! Disponibili: {deposito_attuale}")
            nuovo_deposito = deposito_attuale - quantita
            nuovo_negozio = negozio_attuale + quantita
        else:
            if negozio_attuale < quantita:
                raise HTTPException(status_code=400, detail=f"Giacenza insufficiente in Negozio! Disponibili: {negozio_attuale}")
            nuovo_deposito = deposito_attuale + quantita
            nuovo_negozio = negozio_attuale - quantita

        supabase.schema("gestionale_divise").table("articoli").update({
            "giacenza_deposito": nuovo_deposito,
            "giacenza_negozio": nuovo_negozio
        }).eq("id", articolo_id).execute()

        return {
            "status": "success",
            "message": "Trasferimento completato con successo!",
            "giacenza_deposito": nuovo_deposito,
            "giacenza_negozio": nuovo_negozio
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# SINCRONIZZAZIONE SHOPIFY
# ==========================================

@app.post("/api/sync-shopify-customers")
def sync_shopify_customers(payload_data: Dict[str, Any]):
    try:
        azienda_id = payload_data.get("azienda_id", 1)

        if not SHOPIFY_SHOP or not SHOPIFY_CLIENT_ID or not SHOPIFY_CLIENT_SECRET:
            raise HTTPException(status_code=500, detail="Credenziali Shopify mancanti nelle variabili d'ambiente di Render.")

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

        url = f"https://{SHOPIFY_SHOP}/admin/api/{SHOPIFY_API_VERSION}/customers.json?limit=250"
        headers = {
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json"
        }

        all_records = []
        active_customer_ids = []
        sincronizzati = 0

        while url:
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=f"Errore chiamata clienti Shopify: {response.text}")
            
            data = response.json()
            customers = data.get("customers", [])

            if not customers:
                break

            for cust in customers:
                cust_id = cust.get("id")
                active_customer_ids.append(cust_id)
                
                nome = cust.get("first_name", "")
                cognome = cust.get("last_name", "")
                email = cust.get("email", "")
                telefono = cust.get("phone", "")
                
                addresses = cust.get("addresses", [])
                default_address = next((addr for addr in addresses if addr.get("default")), addresses[0] if addresses else {})
                
                ragione_sociale = default_address.get("company", "")
                indirizzo_1 = default_address.get("address1", "")
                indirizzo_2 = default_address.get("address2", "")
                indirizzo_completo = f"{indirizzo_1} {indirizzo_2}".strip()
                
                citta = default_address.get("city", "")
                cap = default_address.get("zip", "")
                provincia = default_address.get("province_code", "")

                record = {
                    "azienda_id": azienda_id,
                    "shopify_customer_id": cust_id,
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

                all_records.append(record)

                if len(all_records) >= 1000:
                    dedup_dict = {r["shopify_customer_id"]: r for r in all_records}
                    batch_dedup = list(dedup_dict.values())
                    supabase.schema("gestionale_divise").table("clienti").upsert(batch_dedup, on_conflict="shopify_customer_id").execute()
                    sincronizzati += len(batch_dedup)
                    all_records = []

            link_header = response.headers.get("Link", "")
            url = None
            if 'rel="next"' in link_header:
                for part in link_header.split(","):
                    if 'rel="next"' in part:
                        url = part.split(";")[0].strip().strip("<>")

        if all_records:
            dedup_dict = {r["shopify_customer_id"]: r for r in all_records}
            batch_dedup = list(dedup_dict.values())
            supabase.schema("gestionale_divise").table("clienti").upsert(batch_dedup, on_conflict="shopify_customer_id").execute()
            sincronizzati += len(batch_dedup)

        return {
            "status": "success",
            "message": f"Sincronizzazione clienti completata! Sincronizzati: {sincronizzati}",
            "total_synced": sincronizzati
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/sync-shopify")
def sync_shopify_products(payload_data: Dict[str, Any]):
    try:
        azienda_id = payload_data.get("azienda_id", 1)

        if not SHOPIFY_SHOP or not SHOPIFY_CLIENT_ID or not SHOPIFY_CLIENT_SECRET:
            raise HTTPException(status_code=500, detail="Credenziali Shopify mancanti.")

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

                    if len(all_records) >= 1000:
                        dedup_dict = {r["shopify_variant_id"]: r for r in all_records}
                        batch_dedup = list(dedup_dict.values())

                        supabase.schema("gestionale_divise").table("articoli").upsert(batch_dedup, on_conflict="shopify_variant_id").execute()
                        sincronizzati += len(batch_dedup)
                        all_records = []

            link_header = response.headers.get("Link", "")
            url = None
            if 'rel="next"' in link_header:
                for part in link_header.split(","):
                    if 'rel="next"' in part:
                        url = part.split(";")[0].strip().strip("<>")

        if all_records:
            dedup_dict = {r["shopify_variant_id"]: r for r in all_records}
            batch_dedup = list(dedup_dict.values())

            supabase.schema("gestionale_divise").table("articoli").upsert(batch_dedup, on_conflict="shopify_variant_id").execute()
            sincronizzati += len(batch_dedup)

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
            "message": f"Sincronizzazione prodotti completata! Aggiornati/Inseriti: {sincronizzati}, Rimossi dal DB: {deleted_count}",
            "total_synced": sincronizzati,
            "total_deleted": deleted_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
