import asyncio
import json
import logging
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn
import os

# Import existing Agent code
from agent_app import create_claude_model, SYSTEM_PROMPT
from task_graph import run_main_sequence_cli

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Robot Control Center - Action Library Mode")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
class AppState:
    def __init__(self):
        self.action_lib = None
        self.llm = None
        self.connected_clients = []
        self.chat_history = []
        self.agent_ready = False

state = AppState()

# WebSocket connection management
class ConnectionManager:
    def __init__(self):
        self.active_connections = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected, current connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"Client disconnected, current connections: {len(self.active_connections)}")

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Failed to broadcast message: {e}")
                self.disconnect(connection)

manager = ConnectionManager()

# Initialize Agent
async def initialize_agent():
    """Initialize Action Library and LLM"""
    try:
        logger.info("Initializing Agent with Action Library...")
        
        # 1. Initialize Action Library
        try:
            from mtc_action_library import get_action_library
            state.action_lib = get_action_library()
            actions = state.action_lib.get_actions()
            logger.info(f"✅ Action Library loaded: {', '.join(actions)}")
        except Exception as e:
            logger.error(f"Failed to initialize Action Library: {e}")
            logger.error("Please ensure workspace is built and sourced")
            state.agent_ready = False
            return
        
        # 2. Create Claude model (for conversational responses)
        try:
            state.llm = create_claude_model()
            logger.info("✅ Claude Sonnet 4 model loaded")
        except Exception as e:
            logger.error(f"Failed to create Claude model: {e}")
            logger.error("Please set ANTHROPIC_API_KEY environment variable")
            # Action library still works, just no conversational responses
        
        state.agent_ready = True
        logger.info("🤖 Agent initialization completed!")
        
        # Broadcast status update
        await manager.broadcast(json.dumps({
            "type": "agent_ready",
            "action_library": actions if state.action_lib else [],
            "llm_available": state.llm is not None
        }))
        
    except Exception as e:
        logger.error(f"Agent initialization failed: {e}")
        state.agent_ready = False

async def ws_reporter(event: dict):
    """Broadcast task graph events to frontend."""
    await manager.broadcast(json.dumps({
        "type": "task_event",
        "event": event,
        "timestamp": datetime.now().isoformat()
    }))

# API routes
@app.get("/api/status")
async def get_status():
    """Get system status"""
    actions = []
    if state.action_lib:
        try:
            actions = state.action_lib.get_actions()
        except:
            pass
    
    return {
        "agent_ready": state.agent_ready,
        "action_library_available": state.action_lib is not None,
        "actions": actions,
        "llm_available": state.llm is not None,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/stats")
async def get_stats():
    """Get action library statistics"""
    if not state.action_lib:
        return {"error": "Action library not initialized"}
    
    try:
        stats = state.action_lib.get_stats()
        return {
            "stats": stats,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": str(e)}

# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    
    try:
        # Send initial status
        actions = []
        if state.action_lib:
            try:
                actions = state.action_lib.get_actions()
            except:
                pass
        
        await websocket.send_text(json.dumps({
            "type": "status",
            "agent_ready": state.agent_ready,
            "action_library_available": state.action_lib is not None,
            "actions": actions,
            "llm_available": state.llm is not None
        }))
        
        # Send chat history
        await websocket.send_text(json.dumps({
            "type": "chat_history",
            "messages": state.chat_history
        }))
        
        while True:
            # Receive message
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            if message_data["type"] == "chat":
                await handle_chat_message(message_data["message"], websocket)
            elif message_data["type"] == "run_main":
                await handle_run_main(message_data.get("prompt", ""))
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)

async def handle_chat_message(message: str, websocket: WebSocket):
    """Handle chat messages (conversational Q&A only, no robot control)"""
    try:
        # Add user message to history
        user_msg = {
            "role": "user",
            "content": message,
            "timestamp": datetime.now().isoformat()
        }
        state.chat_history.append(user_msg)
        
        # Broadcast user message
        await manager.broadcast(json.dumps({
            "type": "message",
            "message": user_msg
        }))
        
        if not state.llm:
            error_msg = {
                "role": "assistant",
                "content": "❌ LLM not initialized. Conversational responses unavailable.",
                "timestamp": datetime.now().isoformat()
            }
            state.chat_history.append(error_msg)
            await manager.broadcast(json.dumps({
                "type": "message",
                "message": error_msg
            }))
            return
        
        # Send "thinking" status
        await manager.broadcast(json.dumps({
            "type": "thinking",
            "thinking": True
        }))
        
        # Call LLM for conversational response (no tool calling)
        try:
            response = await state.llm.ainvoke([{"role": "user", "content": message}])
            agent_response = response.content
        except Exception as e:
            logger.error(f"LLM invocation failed: {e}")
            agent_response = f"❌ Error: {str(e)}"
        
        agent_msg = {
            "role": "assistant",
            "content": agent_response,
            "timestamp": datetime.now().isoformat()
        }
        
        # Add to history
        state.chat_history.append(agent_msg)
        
        # Send Agent response
        await manager.broadcast(json.dumps({
            "type": "message",
            "message": agent_msg
        }))
        
        # Cancel "thinking" status
        await manager.broadcast(json.dumps({
            "type": "thinking", 
            "thinking": False
        }))
        
    except Exception as e:
        logger.error(f"Failed to process message: {e}")
        error_msg = {
            "role": "assistant",
            "content": f"❌ Error processing message: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }
        state.chat_history.append(error_msg)
        await manager.broadcast(json.dumps({
            "type": "message",
            "message": error_msg
        }))
        await manager.broadcast(json.dumps({
            "type": "thinking",
            "thinking": False
        }))

async def handle_run_main(prompt: str):
    """Trigger main flow through WebSocket and push events step by step."""
    try:
        if not state.agent_ready:
            await manager.broadcast(json.dumps({
                "type": "task_error", 
                "error": "Agent not ready. Please wait for initialization."
            }))
            return
        
        await manager.broadcast(json.dumps({"type": "task_start", "prompt": prompt}))
        # task_graph不再需要tools参数
        summary = await run_main_sequence_cli(prompt, reporter=ws_reporter)
        await manager.broadcast(json.dumps({"type": "task_summary", "summary": summary}))
    except Exception as e:
        logger.error(f"Task execution error: {e}")
        await manager.broadcast(json.dumps({"type": "task_error", "error": str(e)}))

# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize when application starts"""
    logger.info("🚀 Starting Robot Control Center - Action Library Mode...")
    asyncio.create_task(initialize_agent())

# Static file service
if os.path.exists("simple_frontend/build"):
    app.mount("/", StaticFiles(directory="simple_frontend/build", html=True), name="static")

if __name__ == "__main__":
    print("🚀 Starting Robot Control Center - Action Library Mode...")
    print("📱 Frontend: http://localhost:8000")
    print("🔧 API Documentation: http://localhost:8000/docs")
    print("🔌 WebSocket: ws://localhost:8000/ws")
    print("\nNote: This version uses direct Action Library integration")
    print("      (no MCP middleware layer)")
    
    uvicorn.run(
        "simple_backend:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
