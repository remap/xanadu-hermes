import asyncio
import logging
import os
import random
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI()

# A global set to keep track of connected terminal WebSocket clients.
connected_terminal_websockets: set[WebSocket] = set()

class WebSocketLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        message = self.format(record)
        for ws in list(connected_terminal_websockets):
            asyncio.create_task(self.send_message(ws, message))

    async def send_message(self, ws: WebSocket, message: str) -> None:
        try:
            await ws.send_text(message)
        except Exception:
            connected_terminal_websockets.discard(ws)

# Set up our logger.
logger = logging.getLogger("live_logger")
logger.setLevel(logging.DEBUG)
ws_handler = WebSocketLogHandler()
ws_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(ws_handler)


@app.post("/urlinput")
async def submit_input(request: Request):
    data = await request.json()
    user_input = data.get("input", "")
    logger.info(f"Received input from client: {user_input}")
    return JSONResponse({"status": "ok"})

@app.websocket("/log")
async def log_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    connected_terminal_websockets.add(websocket)
    client_host, client_port = websocket.client
    logger.info(f"New connection from {client_host}:{client_port}")
    try:
        while True:
            await websocket.receive_text()  # Keep the connection open.
    except WebSocketDisconnect:
        connected_terminal_websockets.discard(websocket)


# Global cache for the latest dynamic HTML fragment.
dynamic_html_cache: str = ""

# A global set to keep track of connected dynamic HTML WebSocket clients.
dynamic_html_clients: set[WebSocket] = set()

@app.websocket("/dynamic")
async def dynamic_html_endpoint(websocket: WebSocket):
    await websocket.accept()
    # Add client to our global set.
    dynamic_html_clients.add(websocket)
    try:
        # If we have a cached HTML fragment, send it immediately.
        if dynamic_html_cache:
            await websocket.send_text(dynamic_html_cache)
        # Keep the connection open.
        while True:
            # You can use a long sleep here; the purpose is just to keep the connection alive.
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        dynamic_html_clients.discard(websocket)


# Serve the main HTML file (client code) from the root URL.
@app.get("/")
async def get_index():
    return FileResponse(os.path.join("html", "index.html"))

# Mount static assets under "/static" (if any).
app.mount("/static", StaticFiles(directory="html", html=True), name="static")

async def generate_test_logs() -> None:
    count = 0
    while True:
        if connected_terminal_websockets:  # Only log if at least one terminal client is connected.
            logger.info(f"Log message #{count}")
            count += 1
        await asyncio.sleep(0.25)


async def heartbeat() -> None:
    while True:
        # Send a "ping" to terminal clients.
        for ws in list(connected_terminal_websockets):
            try:
                await ws.send_text("<<ping>>")
            except Exception:
                connected_terminal_websockets.discard(ws)
        # Also ping dynamic clients if desired.
        for ws in list(dynamic_html_clients):
            try:
                await ws.send_text("<<ping>>")
            except Exception:
                dynamic_html_clients.discard(ws)
        await asyncio.sleep(30)

def gen_html() -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    random_number = random.randint(1, 100)
    return f"""
    <!DOCTYPE html>
    <html>
      <head>
        <meta charset="UTF-8">
        <title>Dynamic HTML Update</title>
      </head>
      <body style="background-color:#000; color:#fff; margin:0; padding:1em;">
        <h1>Dynamic HTML Content</h1>
        <p>Updated at {now}</p>
        <p>Random number: {random_number}</p>
      </body>
    </html>
    """

async def run_oracle() -> None:
    global dynamic_html_cache
    logger.info("run_oracle()")
    while True:
        # Wait between 1 and 10 seconds.
        logger.debug("Waiting...")
        await asyncio.sleep(random.randint(1, 10))
        logger.debug("Generating")
        dynamic_html_cache = gen_html()
        # Broadcast the new HTML to all connected dynamic clients.
        logger.debug("Broadcasting")
        disconnected = set()
        for client in dynamic_html_clients:
            try:
                await client.send_text(new_html)
            except Exception:
                disconnected.add(client)
        # Remove any clients that failed.
        for client in disconnected:
            dynamic_html_clients.discard(client)
        logger.debug("Complete")

@app.on_event("startup")
async def startup_event() -> None:
    #asyncio.create_task(generate_test_logs())
    asyncio.create_task(run_oracle())
    asyncio.create_task(heartbeat())

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
