import json
import asyncio
from typing import Annotated
import re
import sqlite3
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from api.niche_agent import app as agent_app
from api.niche_agent import DB_PATH

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SAFE_TABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_table_name(table_name: str) -> str:
    if not SAFE_TABLE_NAME.fullmatch(table_name):
        raise HTTPException(status_code=400, detail="Invalid table name.")
    return table_name


@app.get("/db/tables")
def list_db_tables():
    try:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        return {"tables": [row[0] for row in rows]}
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail=f"Failed to list tables: {exc}") from exc


@app.get("/db/table/{table_name}")
def read_db_table(
    table_name: str,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
):
    safe_table = _validate_table_name(table_name)
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(f'SELECT * FROM "{safe_table}" ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
        return {
            "table": safe_table,
            "count": len(rows),
            "rows": [dict(row) for row in rows],
        }
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read table '{safe_table}': {exc}") from exc


@app.delete("/db/table/{table_name}/purge")
def purge_db_table(table_name: str):
    safe_table = _validate_table_name(table_name)
    try:
        with sqlite3.connect(DB_PATH) as conn:
            deleted = conn.execute(f'DELETE FROM "{safe_table}"').rowcount
            conn.commit()
        return {"table": safe_table, "deleted_rows": deleted}
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail=f"Failed to purge table '{safe_table}': {exc}") from exc

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
