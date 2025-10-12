# Realtime Demo App

A web-based realtime voice assistant demo with a FastAPI backend and HTML/JS frontend.

## Installation

Install the required dependencies:

```bash
uv add fastapi uvicorn websockets
```

## Usage

Start the application with a single command:

```bash
cd examples/realtime/app && uv run python server.py
```

Then open your browser to: http://localhost:8000

## Customization

To use the same UI with your own agents, edit `agent.py` and ensure get_starting_agent() returns the right starting agent for your use case.

## How to Use

1. Click **Connect** to establish a realtime session
2. Audio capture starts automatically - just speak naturally
3. Click the **Mic On/Off** button to mute/unmute your microphone
4. To send an image, enter an optional prompt and click **🖼️ Send Image** (select a file)
5. Watch the conversation unfold in the left pane (image thumbnails are shown)
6. Monitor raw events in the right pane (click to expand/collapse)
7. Click **Disconnect** when done

## Architecture

-   **Backend**: FastAPI server with WebSocket connections for real-time communication
-   **Session Management**: Each connection gets a unique session with the OpenAI Realtime API
-   **Image Inputs**: The UI uploads images and the server forwards a
    `conversation.item.create` event with `input_image` (plus optional `input_text`),
    followed by `response.create` to start the model response. The messages pane
    renders image bubbles for `input_image` content.
-   **Audio Processing**: 24kHz mono audio capture and playback
-   **Event Handling**: Full event stream processing with transcript generation
-   **Frontend**: Vanilla JavaScript with clean, responsive CSS

The demo showcases the core patterns for building realtime voice applications with the OpenAI Agents SDK.

## Pizza Ordering MVP (TR/EN/NL)

This app now includes a minimal pizza ordering flow implemented with two agents and a few tools. Existing demo usage remains the same; this section documents the ordering features.

- Agents
  - `TriageAgent`: Detects the conversation language from the first user utterance (Turkish/English/Dutch), locks it for the session, reprompts briefly on silence/small talk, and hands off to OrderAgent when the user intends to “order” (`sipariş/vermek/order/bestellen`).
  - `OrderAgent`: Gathers pizza items and quantities, a single size for all pizzas, optional drinks, then reads a summary and asks for confirmation. All writes go through the Order State tools.

- Canonical Menu
  - Pizzas: Margherita, Pepperoni, Vegan Margherita, BBQ Meat Lovers, Caprese
  - Drinks: Coca-Cola 330ml, Coca-Cola Zero 330ml, Fanta 330ml, Red Bull, Spa Blauw
  - Sizes: 25cm, 30cm, 35cm

- Tools
  - Inventory
    - `inventory_list_pizzas()`
    - `inventory_list_drinks()`
    - `inventory_normalize_item(text)` — naive alias normalization for pizzas/drinks
  - Order State (process-global MVP store)
    - `order_state_clear()` — reset state on first turn after handoff
    - `order_state_add_item(product_name, quantity)`
    - `order_state_set_size_for_all(size)` — accepts `25`, `30`, `35` or `25cm/30cm/35cm`
    - `order_state_add_drink(product_name, quantity)`
    - `order_state_summary()` — returns items, drinks, size_all, total
    - `order_state_confirm()` — returns a generated `order_id`

- Short Prompts (multi-lingual)
  - Triage (first line):
    - TR: “Merhaba! Sipariş vermek ister misiniz?”
    - EN: “Hi! Would you like to place an order?”
    - NL: “Hoi! Wilt u een bestelling plaatsen?”
  - Order steps:
    - Product+Qty: TR “Hangi pizzalar ve kaç adet?” | EN “Which pizzas and how many?” | NL “Welke pizza’s en hoeveel?”
    - Size: TR “Hepsi için boyut? 25, 30 veya 35 cm.” | EN “Size for all? 25, 30 or 35 cm.” | NL “Maat voor alle pizza’s? 25, 30 of 35 cm.”
    - Drink: TR “İçecek ister misiniz?” | EN “Any drinks?” | NL “Wilt u drankjes?”
    - Summary/Confirm: TR “Özet: {summary}. Onaylıyor musunuz?” | EN “Summary: {summary}. Confirm?” | NL “Samenvatting: {summary}. Bevestigen?”

- Expected Test Flow
  - User: “Merhaba, bir sipariş verecektim.” → Triage detects TR and hands off to Order.
  - Order: “Hangi pizzalar ve kaç adet?”
  - User: “2 pepperoni, 1 margherita.” → add items
  - Order: “Hepsi için boyut? 25, 30 veya 35 cm.”
  - User: “30.” → set size for all (30cm)
  - Order: “İçecek ister misiniz?”
  - User: “2 kola zero.” → add drinks
  - Order: “Özet: … Toplam: €… Onaylıyor musunuz?” → confirm
  - User: “Evet.” → confirm; returns `order_id`

- Notes
  - State is maintained in a simple process-global dictionary for MVP simplicity. For multi-session usage, scope order state by session/thread.
  - Normalization is alias-based and intentionally naive; replace with fuzzy matching as needed.
