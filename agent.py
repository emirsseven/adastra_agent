from agents import function_tool
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX
from agents.realtime import RealtimeAgent, realtime_handoff
import re
import unicodedata
import difflib

"""
Local UI example entrypoint. The server will use get_starting_agent() as
the starting agent.
This file defines a minimal pizza-ordering MVP with a Triage and Order agent,
plus inventory and order-state tools.
"""

# --- Inventory ---
PIZZAS = [
    {"id": "p_margherita", "name": "Margherita", "price": 9.5},
    {"id": "p_pepperoni", "name": "Pepperoni", "price": 10.5},
    {"id": "p_vegan_margherita", "name": "Vegan Margherita", "price": 10.5},
    {"id": "p_bbq_meat_lovers", "name": "BBQ Meat Lovers", "price": 12.0},
    {"id": "p_caprese", "name": "Caprese", "price": 11.0},
]

DRINKS = [
    {"id": "d_coke", "name": "Coca-Cola 330ml", "price": 2.5},
    {"id": "d_coke_zero", "name": "Coca-Cola Zero 330ml", "price": 2.5},
    {"id": "d_fanta", "name": "Fanta 330ml", "price": 2.5},
    {"id": "d_rb", "name": "Red Bull", "price": 3.0},
    {"id": "d_spa", "name": "Spa Blauw", "price": 2.0},
]

SIZES = ["25cm", "30cm", "35cm"]

OFF_TOPIC_REPLY = {
    "TR": "Bu asistan yalnızca pizza siparişi konusunda yardımcı olur. Diğer konuları konuşamıyorum. Sipariş vermek ister misiniz?",
    "EN": "I can only help with pizza orders. I can’t discuss other topics. Would you like to place an order?",
    "NL": "Ik help alleen met pizzabestellingen. Andere onderwerpen kan ik niet bespreken. Wilt u een bestelling plaatsen?",
}


# --- Order state (simple in‑process MVP store) ---
# Note: This demo keeps a single global state instance. In a multi-session
# setup you would scope this by session/thread.
ORDER_STATE = {
    "items": [],  # list[{name, qty, size}]
    "drinks": [],  # list[{name, qty}]
    "size_all": None,
}


def _prices_by_name() -> dict:
    return {x["name"]: x["price"] for x in (PIZZAS + DRINKS)}


def _normalize_size(size: str) -> str | None:
    if not size:
        return None
    s = str(size).lower().strip().replace(" ", "")
    if s.endswith("cm"):
        s2 = s
    else:
        s2 = f"{s}cm" if s.isdigit() else s
    return s2 if s2 in SIZES else None


# --- Inventory Tools ---
@function_tool(name_override="inventory_list_pizzas")
def inventory_list_pizzas() -> list[dict]:
    return PIZZAS


@function_tool(name_override="inventory_list_drinks")
def inventory_list_drinks() -> list[dict]:
    return DRINKS


@function_tool(name_override="inventory_normalize_item")
def inventory_normalize_item(text: str) -> dict:
    """Return canonical name/type for a free-text item using robust normalization."""
    if not text:
        return {"canonical_name": None, "type": None, "confidence": 0.0}

    def _strip_accents(s: str) -> str:
        return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))

    raw = _strip_accents(str(text).lower())
    raw = re.sub(r"[^a-z0-9\s]", " ", raw)
    stop = {"pizza", "adet", "tane", "pcs", "piece", "stuks", "cm"}
    tokens = [tok for tok in raw.split() if tok not in stop and not tok.isdigit()]
    t = " ".join(tokens).strip()

    aliases = {
        # pizzas
        "margerita": "Margherita",
        "margarita": "Margherita",
        "margherita": "Margherita",
        "margharita": "Margherita",
        "pepperoni": "Pepperoni",
        "peperoni": "Pepperoni",
        "pepproni": "Pepperoni",
        "vegan margerita": "Vegan Margherita",
        "vegan margherita": "Vegan Margherita",
        "vegan margarita": "Vegan Margherita",
        "bbq meat": "BBQ Meat Lovers",
        "barbeku meat": "BBQ Meat Lovers",
        "bbq": "BBQ Meat Lovers",
        "barbeku met lavirs": "BBQ Meat Lovers",
        "bbq meat lovers": "BBQ Meat Lovers",
        "bebequ mit lovers": "BBQ Meat Lovers",
        "caprese": "Caprese",
        "kaprese": "Caprese",
        "capriese": "Caprese",
        "kapriese": "Caprese",

        # drinks
        "kola": "Coca-Cola 330ml",
        "koka kola": "Coca-Cola 330ml",
        "coca cola": "Coca-Cola 330ml",
        "coke": "Coca-Cola 330ml",
        "coke zero": "Coca-Cola Zero 330ml",
        "kola zero": "Coca-Cola Zero 330ml",
        "koka kola zero": "Coca-Cola Zero 330ml",
        "coca cola zero": "Coca-Cola Zero 330ml",
        "fanta": "Fanta 330ml",
        "red bull": "Red Bull",
        "spa": "Spa Blauw",
        "spa blauw": "Spa Blauw",
        "sipa blauv": "Spa Blauw",
        
    }
    # substring match (prefer longest key)
    sub_matches = [k for k in aliases.keys() if k in t]
    if sub_matches:
        key = max(sub_matches, key=len)
        name = aliases[key]
        typ = "pizza" if any(p["name"] == name for p in PIZZAS) else "drink"
        return {"canonical_name": name, "type": typ, "confidence": 0.95}

    # fuzzy match against aliases and canonical names
    keys = list(aliases.keys()) + [p["name"].lower() for p in PIZZAS] + [d["name"].lower() for d in DRINKS]
    best = difflib.get_close_matches(t, keys, n=1, cutoff=0.85)
    if best:
        k = best[0]
        name = (
            aliases.get(k)
            or next((p["name"] for p in PIZZAS if p["name"].lower() == k), None)
            or next((d["name"] for d in DRINKS if d["name"].lower() == k), None)
        )
        if name:
            typ = "pizza" if any(p["name"] == name for p in PIZZAS) else "drink"
            return {"canonical_name": name, "type": typ, "confidence": 0.88}

    return {"canonical_name": None, "type": None, "confidence": 0.0}


# --- Order State Tools ---
@function_tool(name_override="order_state_clear")
def order_state_clear() -> str:
    ORDER_STATE["items"] = []
    ORDER_STATE["drinks"] = []
    ORDER_STATE["size_all"] = None
    return "cleared"


@function_tool(name_override="order_state_add_item")
def order_state_add_item(product_name: str, quantity: int) -> dict:
    q = max(1, int(quantity))
    ORDER_STATE["items"].append({"name": product_name, "qty": q, "size": ORDER_STATE["size_all"]})
    return {"ok": True, "items": ORDER_STATE["items"]}


@function_tool(name_override="order_state_set_size_for_all")
def order_state_set_size_for_all(size: str) -> dict:
    s = _normalize_size(size)
    if not s:
        return {"ok": False, "error": "invalid_size", "allowed": SIZES}
    ORDER_STATE["size_all"] = s
    for it in ORDER_STATE["items"]:
        it["size"] = s
    return {"ok": True, "size_all": s, "items": ORDER_STATE["items"]}


@function_tool(name_override="order_state_add_drink")
def order_state_add_drink(product_name: str, quantity: int) -> dict:
    q = max(1, int(quantity))
    ORDER_STATE["drinks"].append({"name": product_name, "qty": q})
    return {"ok": True, "drinks": ORDER_STATE["drinks"]}


@function_tool(name_override="order_state_summary")
def order_state_summary() -> dict:
    prices = _prices_by_name()
    total = 0.0
    for it in ORDER_STATE["items"]:
        total += prices.get(it["name"], 0.0) * int(it.get("qty", 1))
    for dr in ORDER_STATE["drinks"]:
        total += prices.get(dr["name"], 0.0) * int(dr.get("qty", 1))
    return {
        "items": ORDER_STATE["items"],
        "drinks": ORDER_STATE["drinks"],
        "size_all": ORDER_STATE["size_all"],
        "total": round(total, 2),
    }


@function_tool(name_override="order_state_confirm")
def order_state_confirm() -> dict:
    import uuid
    return {"order_id": "ORD-" + uuid.uuid4().hex[:8].upper()}


# --- Agents ---
# Multi-lingual short prompts (TR/EN/NL)
TRIAGE_GREET = {
    "TR": "Merhaba! Sipariş vermek ister misiniz?",
    "EN": "Hi! Would you like to place an order?",
    "NL": "Hoi! Wilt u een bestelling plaatsen?",
}

ORDER_PROMPTS = {
    "PRODUCT_QTY": {
        "TR": "Hangi pizzalar ve kaç adet?",
        "EN": "Which pizzas and how many?",
        "NL": "Welke pizza’s en hoeveel?",
    },
    "SIZE": {
        "TR": "Hepsi için boyut? 25, 30 veya 35 cm.",
        "EN": "Size for all? 25, 30 or 35 cm.",
        "NL": "Maat voor alle pizza’s? 25, 30 of 35 cm.",
    },
    "DRINK": {
        "TR": "İçecek ister misiniz?",
        "EN": "Any drinks?",
        "NL": "Wilt u drankjes?",
    },
    "SUMMARY": {
        "TR": "Özet: {summary}. Onaylıyor musunuz?",
        "EN": "Summary: {summary}. Confirm?",
        "NL": "Samenvatting: {summary}. Bevestigen?",
    },
}


triage_agent = RealtimeAgent(
    name="TriageAgent",
    handoff_description="Detects language (TR/EN/NL), reprompts briefly on silence, and hands off to OrderAgent for ordering.",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
You are a triage agent. From the user's FIRST utterance only, detect the language among Turkish/English/Dutch and silently lock a variable language to that value. Always speak in that locked language. Do NOT re-detect on subsequent turns.

Domain boundary: This assistant ONLY handles pizza ordering (menu items, quantities, sizes, drinks). It must politely refuse and redirect ANY other topic (e.g., politics, news, programming, general chit‑chat, or image/video analysis not clearly related to ordering). Never claim additional capabilities. Do not mention that you can analyze images.

Off‑topic refusal (respond in the locked language using the matching line):
- TR: {OFF_TOPIC_REPLY['TR']}
- EN: {OFF_TOPIC_REPLY['EN']}
- NL: {OFF_TOPIC_REPLY['NL']}

If the user's intent includes ordering (keywords like: 'sipariş', 'vermek', 'order', 'bestellen'), perform a handoff to OrderAgent.
On small talk, silence, or off‑topic content, answer with the off‑topic refusal (in the locked language) and repeat the greeting.
If the user sends an image: only proceed if it clearly shows pizza or a menu relevant to ordering; otherwise reply with the off‑topic refusal.

Use the following first-line greeting in the locked language only (do not show other languages):
- TR: {TRIAGE_GREET['TR']}
- EN: {TRIAGE_GREET['EN']}
- NL: {TRIAGE_GREET['NL']}
""",
)


order_agent = RealtimeAgent(
    name="OrderAgent",
    handoff_description="Collects pizza order details and confirms.",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
You are the order agent. The conversation language is fixed as language from triage; respond only in that language.

Goal: Collect pizza names and quantities (canonical menu only), then a single size for all pizzas (allowed: 25cm/30cm/35cm), then whether they want drinks, then read a summary and ask for confirmation.

Strict domain rules:
- This agent only handles pizza ordering. If the user asks about anything else (e.g., politics, news, coding, general Q&A, or image analysis unrelated to ordering), do NOT answer. Politely refuse and immediately steer back to ordering using the off‑topic line for the locked language: TR/EN/NL -> {OFF_TOPIC_REPLY['TR']} / {OFF_TOPIC_REPLY['EN']} / {OFF_TOPIC_REPLY['NL']}.
- Do not claim additional capabilities beyond taking orders. Do not offer to analyze images unless they clearly support choosing items from the menu.

Operational rules:
- On your first turn after handoff, call order_state_clear() to reset state.
- Use Inventory tools to validate or normalize items (inventory_normalize_item). Accept only canonical names from the menu.
- When calling inventory_normalize_item, pass only product name tokens (no quantities or sizes).
- Use Order State tools for ALL writes: order_state_add_item, order_state_set_size_for_all, order_state_add_drink, order_state_summary, order_state_confirm.
- If input is invalid or uncertain, briefly reprompt. Ignore unrelated topics entirely (use refusal + steer back).
- Ask only what is necessary; proceed step-by-step.

Step prompts (respond in the locked language):
- Product+Qty: TR: {ORDER_PROMPTS['PRODUCT_QTY']['TR']} | EN: {ORDER_PROMPTS['PRODUCT_QTY']['EN']} | NL: {ORDER_PROMPTS['PRODUCT_QTY']['NL']}
- Size: TR: {ORDER_PROMPTS['SIZE']['TR']} | EN: {ORDER_PROMPTS['SIZE']['EN']} | NL: {ORDER_PROMPTS['SIZE']['NL']}
- Drink: TR: {ORDER_PROMPTS['DRINK']['TR']} | EN: {ORDER_PROMPTS['DRINK']['EN']} | NL: {ORDER_PROMPTS['DRINK']['NL']}
- Summary/Confirm: TR/EN/NL template above; call order_state_summary() then ask to confirm.
""",
    tools=[
        inventory_list_pizzas,
        inventory_list_drinks,
        inventory_normalize_item,
        order_state_clear,
        order_state_add_item,
        order_state_set_size_for_all,
        order_state_add_drink,
        order_state_summary,
        order_state_confirm,
    ],
)


# Configure handoffs
triage_agent.handoffs = [realtime_handoff(order_agent)]
order_agent.handoffs = [realtime_handoff(triage_agent)]


def get_starting_agent() -> RealtimeAgent:
    return triage_agent
