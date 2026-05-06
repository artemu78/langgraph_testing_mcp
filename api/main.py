import json
import asyncio
from typing import Annotated
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from api.niche_agent import app as agent_app

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/research")
async def research(keyword: Annotated[str, Query()]):
    async def event_generator():
        initial_input = {
            "keyword": keyword,
            "iterations": 0,
            "should_research_again": False,
            "logs": [f"Agent initialized for: {keyword}"]
        }
        
        # Stream updates from the graph
        # Using a sync-to-async wrapper if necessary, but app.stream is sync if not configured otherwise.
        # However, for SSE we need to yield.
        
        try:
            # Run in a thread if app.stream is blocking
            # Or use astream if supported (LangGraph supports astream)
            async for update in agent_app.astream(initial_input, stream_mode="updates"):
                # update is a dict: {node_name: {state_delta}}
                node_name = list(update.keys())[0]
                data = update[node_name]
                
                payload = {
                    "node": node_name,
                    "logs": data.get("logs", []),
                    "status": "running"
                }
                
                # Check if it's the last node or contains final results
                if "verification" in data:
                    payload["final_result"] = {
                        "strategy": data.get("strategy"),
                        "verification": data.get("verification")
                    }
                
                yield f"data: {json.dumps(payload)}\n\n"
                await asyncio.sleep(0.5) # Small delay for visual effect
            
            # Final message
            yield f"data: {json.dumps({'status': 'completed'})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
