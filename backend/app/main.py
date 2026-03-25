from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import tasks, decisions, agents, websocket

app = FastAPI(title="Project Million", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks.router)
app.include_router(decisions.router)
app.include_router(agents.router)
app.include_router(websocket.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
