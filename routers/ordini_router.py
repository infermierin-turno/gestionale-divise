from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from database import supabase

router = APIRouter(tags=["Shopify Ordini"])

@router.post("/api/shopify/webhook/orders")
@router.post("/api/ordini/shopify")
def ricevi_ordine_shopify(payload_data: Dict[str, Any]):
    """
    Riceve il webhook degli ordini da Shopify, gestisce/crea il cliente in anagrafica 
    e salva l'ordine nella tabella dedicata gestionale_divise.ordini.
    """
    try:
        # 1. Estrazione dati cliente da Shopify
        customer_data = payload_data.get("customer", {})
        email = customer_data.get("email") or payload_data.get("contact_email")
        
        cliente_id = None
        
        if email:
            # Verifica se il cliente esiste già per email nello schema gestionale_divise
            resp_cliente = supabase.schema("gestionale_divise").table("clienti").select("id").eq("email", email).execute()
            if resp_cliente.data and len(resp_cliente.data) > 0:
                cliente_id = resp_cliente.data[0]["id"]
        
        # Se il cliente non esiste, lo creiamo al volo
        if not cliente_id:
            shipping = payload_data.get("shipping_address", {})
            billing = payload_data.get("billing_address", {})
            address = shipping if shipping else billing
            
            nuovo_cliente = {
                "azienda_id": 1,
                "nome": customer_data.get("first_name", ""),
                "cognome": customer_data.get("last_name", ""),
                "ragione_sociale": address.get("company", ""),
                "email": email,
                "telefono": customer_data.get("phone") or address.get("phone", ""),
                "indirizzo": address.get("address1", ""),
                "citta": address.get("city", ""),
                "cap": address.get("zip", ""),
                "provincia": address.get("province_code", ""),
            }
            
            resp_new_cli = supabase.schema("gestionale_divise").table("clienti").insert(nuovo_cliente).execute()
            if resp_new_cli.data:
                cliente_id = resp_new_cli.data[0]["id"]

        # 2. Estrazione dati economici e di spedizione dell'ordine
        shopify_order_id = payload_data.get("id")
        shopify_order_name = str(payload_data.get("name", payload_data.get("order_number", "")))
        
        totale_prodotti = float(payload_data.get("subtotal_price", payload_data.get("total_line_items_price", 0.0)))
        
        # Calcolo spedizione dalle shipping lines
        totale_spedizione = 0.0
        shipping_lines = payload_data.get("shipping_lines", [])
        for sl in shipping_lines:
            totale_spedizione += float(sl.get("price", 0.0))
            
        totale_ordine = float(payload_data.get("total_price", 0.0))

        # Verifica se viene richiesta fattura (es. presenza di P.IVA o note fiscali nell'ordine)
        billing_address = payload_data.get("billing_address", {})
        note_ordine = payload_data.get("note", "")
        
        richiede_fattura = False
        if billing_address.get("company") or "fattura" in note_ordine.lower() or payload_data.get("tax_lines"):
            richiede_fattura = True

        # 3. Inserimento nella tabella gestionale_divise.ordini
        ordine_payload = {
            "azienda_id": 1,
            "shopify_order_id": shopify_order_id,
            "shopify_order_name": shopify_order_name,
            "canale_vendita": "Shopify",
            "cliente_id": cliente_id,
            "stato_ordine": "nuovo",
            "totale_prodotti": totale_prodotti,
            "totale_spedizione": totale_spedizione,
            "totale_ordine": totale_ordine,
            "richiede_fattura": richiede_fattura,
            "fattura_emessa": False,
            "note_personalizzazione": note_ordine if note_ordine else None
        }
        
        resp_ordine = supabase.schema("gestionale_divise").table("ordini").insert(ordine_payload).execute()
        if not resp_ordine.data:
            raise HTTPException(status_code=500, detail="Errore durante il salvataggio dell'ordine nella tabella ordini.")
        
        ordine_creato = resp_ordine.data[0]
        ordine_id = ordine_creato["id"]

        return {
            "status": "success",
            "message": f"Ordine Shopify {shopify_order_name} sincronizzato correttamente!",
            "ordine_id": ordine_id,
            "cliente_id": cliente_id
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
