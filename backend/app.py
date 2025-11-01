import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from db import search_phrase

app = FastAPI(title="YouGlish-lite API", version="0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SearchResponseItem(BaseModel):
    id: int
    video_id: str
    lang: str
    t_start: float
    t_end: float
    text: str
    title: Optional[str] = None
    channel_title: Optional[str] = None

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/search", response_model=list[SearchResponseItem])
def search(q: str, lang: Optional[str] = None, limit: int = 20):
    q = q.strip()
    if not q:
        raise HTTPException(400, detail="q is required")
    rows = search_phrase(q, lang, limit)
    return rows

