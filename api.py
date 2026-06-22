import asyncio
import io
import os
import psutil
import time
import numpy as np

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import ollama
from brain.brain import Brain

app = FastAPI(title="MAYA API Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances
brain_instance = None

@app.on_event("startup")
async def startup_event():
    global brain_instance
    print("[MAYA API] Initializing Brain...")
    brain_instance = Brain(enable_memory=True)
    print("[MAYA API] Ready.")

class ChatRequest(BaseModel):
    message: str
    session_id: str

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    # Process synchronously but in a background thread to not block the event loop
    res = await asyncio.to_thread(brain_instance.process_raw, request.message)
    response_text = res.get("response", "Error processing request.")
    agent_used = None
    if res.get("results") and len(res["results"]) > 0:
        agent_used = res["results"][0].get("agent", None)
    
    return {
        "response": response_text,
        "agent_used": agent_used,
        "thinking_steps": []
    }

@app.get("/api/system/stats")
async def system_stats():
    mem = psutil.virtual_memory()
    return {
        "cpu_percent": psutil.cpu_percent(interval=None),
        "ram_percent": mem.percent,
        "ram_used_gb": mem.used / (1024**3),
        "ram_total_gb": mem.total / (1024**3)
    }

@app.get("/api/memory/stats")
async def memory_stats():
    if not brain_instance or not brain_instance.memory:
        return {"vector_count": 0, "ltm_similarities": []}
        
    status = brain_instance.memory.get_status()
    return {
        "vector_count": status.get("vector_count", 0),
        "ltm_similarities": [0.5, 0.6, 0.55, 0.7, 0.8, 0.6, 0.9, 0.85, 0.7, 0.6, 0.8, 0.9, 0.88] # Mock sparkline data
    }

@app.get("/api/chat/context_usage")
async def context_usage():
    if not brain_instance or not brain_instance.memory:
        return {"turns_loaded": 0, "max_turns": 20}
        
    messages = brain_instance.memory.active_chat.get_all_messages()
    return {
        "turns_loaded": len(messages),
        "max_turns": 20
    }

@app.get("/api/status")
async def get_status():
    ollama_ok = "error"
    model_name = "unknown"
    try:
        models = ollama.list()
        if models and "models" in models and len(models["models"]) > 0:
            ollama_ok = "ok"
            # Attempt to grab the first loaded model name or default config
            from brain.utils.config import RESPONSE_MODEL
            model_name = RESPONSE_MODEL
    except Exception:
        pass
        
    return {
        "backend": "ok",
        "ollama": ollama_ok,
        "model": model_name,
        "voice": "ready"
    }

@app.post("/api/voice/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)):
    try:
        # Save temp audio file
        audio_bytes = await audio.read()
        temp_file = "temp_transcribe.webm"
        with open(temp_file, "wb") as f:
            f.write(audio_bytes)
            
        # Use whisper model directly
        from voice.voice_orchestrator import _ensure_loaded, _wake_model
        _ensure_loaded()
        
        # We can transcribe a file using faster_whisper
        segments, _ = _wake_model.transcribe(
            temp_file, beam_size=5, language="en", condition_on_previous_text=False
        )
        text = " ".join([segment.text for segment in segments]).strip()
        
        if os.path.exists(temp_file):
            os.remove(temp_file)
            
        return {"text": text}
    except Exception as e:
        print(f"[API] Error in transcription: {e}")
        return {"text": ""}

@app.get("/api/agents")
async def list_agents():
    """Return the live agent list from the registry for the frontend HUD."""
    if not brain_instance:
        return {"agents": []}

    agents = []
    for name in brain_instance.list_agents():
        info = brain_instance.registry.get_agent_info(name)
        if info:
            display_name = name.replace("_agent", "").upper()
            agents.append({
                "id": name,
                "display_name": display_name,
                "description": info.get("description", ""),
                "type": info.get("type", "tool"),
                "action_count": info.get("action_count", 0),
            })
    return {"agents": agents}


@app.post("/api/agents/reload")
async def reload_agents():
    """Re-read registry files and clear the agent cache. Call after build_registry.py."""
    if not brain_instance:
        return {"status": "error", "message": "Brain not initialized"}
    brain_instance.reload_registry()
    return {"status": "ok", "agents": brain_instance.list_agents()}


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message")
            
            # Since brain process is sync, run in thread
            res = await asyncio.to_thread(brain_instance.process_raw, message)
            
            response_text = res.get("response", "")
            agent_used = None
            if res.get("results") and len(res["results"]) > 0:
                agent_used = res["results"][0].get("agent", None)
            
            # Stream the final response word by word to emulate typing
            words = response_text.split(" ")
            for i, word in enumerate(words):
                token = word + (" " if i < len(words) - 1 else "")
                await websocket.send_json({"token": token})
                await asyncio.sleep(0.04) # Simulate 40ms typing delay per word
                
            await websocket.send_json({"done": True, "agent_used": agent_used})
            
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[API] Websocket error: {e}")


# ═══════════════════════════════════════════════════════════
# Code Agent endpoints — direct REST access for the frontend
# ═══════════════════════════════════════════════════════════

class CodeStartRequest(BaseModel):
    goal: str
    project_root: str
    dry_run: bool = False
    context: str | None = None

class CodeCancelRequest(BaseModel):
    job_id: str

@app.post("/api/code/start")
async def code_start(req: CodeStartRequest):
    from agents.maya_code_agent import execute
    return execute({
        "action": "start_task",
        "parameters": {
            "goal": req.goal,
            "project_root": req.project_root,
            "dry_run": req.dry_run,
            "context": req.context,
        },
    })

@app.get("/api/code/status/{job_id}")
async def code_status(job_id: str):
    from agents.maya_code_agent import execute
    return execute({"action": "get_status", "parameters": {"job_id": job_id}})

@app.post("/api/code/cancel")
async def code_cancel(req: CodeCancelRequest):
    from agents.maya_code_agent import execute
    return execute({"action": "cancel_task", "parameters": {"job_id": req.job_id}})

@app.get("/api/code/jobs")
async def code_jobs():
    from agents.maya_code_agent import execute
    return execute({"action": "list_jobs", "parameters": {}})
