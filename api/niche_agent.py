import sys
import time
import operator
import json
import urllib.parse
import urllib.request
import os
from typing import Annotated, TypedDict, List, Dict, Literal
from langgraph.graph import StateGraph, START, END

# Delay applied at the start of each node execution.
DELAY_SECONDS = 0.5

# 1. Define the State Schema
class AgentState(TypedDict):
    """The state shared between all nodes in the graph."""
    keyword: str
    trend_data: Dict[str, float]
    anomalies: List[str]
    strategy: str
    verification: str
    # Counter to avoid infinite loops in mock
    iterations: int
    # Using Annotated with operator.add to accumulate logs instead of overwriting
    logs: Annotated[List[str], operator.add]

# 2. Define the Nodes with Mocked Logic

def google_search(query: str, num_results: int = 5) -> List[str]:
    """Runs Google Custom Search API and returns top result snippets.

    Requires:
    - GOOGLE_API_KEY
    - GOOGLE_CSE_ID
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    cse_id = os.getenv("GOOGLE_CSE_ID")

    if not api_key or not cse_id:
        return [
            "Search unavailable: set GOOGLE_API_KEY and GOOGLE_CSE_ID.",
            "Fallback insight: no live SERP data, treat competition level as uncertain.",
        ]

    params = urllib.parse.urlencode(
        {"key": api_key, "cx": cse_id, "q": query, "num": num_results}
    )
    url = f"https://www.googleapis.com/customsearch/v1?{params}"

    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return [f"Search failed: {exc}"]

    items = payload.get("items", [])
    if not items:
        return ["No search results found for this query."]

    return [
        f"{item.get('title', 'Untitled')} | {item.get('link', 'No link')}"
        for item in items
    ]

def trend_researcher(state: AgentState) -> dict:
    """Mocks fetching historical data for a keyword."""
    time.sleep(DELAY_SECONDS)
    iter_info = f" (Round {state.get('iterations', 0) + 1})"
    print(f"--- [Node: Trend Researcher] Researching: {state['keyword']}{iter_info} ---")
    # Mocked data showing a spike for 'breakout_month'
    mock_data = {
        "2023-10": 10.5,
        "2023-11": 12.2,
        "2023-12": 45.8, # Spike here
        "2024-01": 15.1
    }
    return {
        "trend_data": mock_data,
        "logs": [f"Fetched trend data for {state['keyword']}{iter_info}"]
    }

def anomaly_detector(state: AgentState) -> dict:
    """Mocks identifying 'Breakout' spikes in the data."""
    time.sleep(DELAY_SECONDS)
    print("--- [Node: Anomaly Detector] Analyzing spikes ---")
    data = state.get("trend_data", {})
    anomalies = []
    
    # Simple threshold logic for mock
    for date, value in data.items():
        if value > 30:
            anomalies.append(date)
            
    status = f"Found breakout spikes at: {anomalies}" if anomalies else "No spikes detected."
    return {
        "anomalies": anomalies,
        "logs": [status]
    }

def market_strategist(state: AgentState) -> dict:
    """Mocks analyzing spikes and suggesting entry points."""
    time.sleep(DELAY_SECONDS)
    print("--- [Node: Market Strategist] Developing strategy ---")
    anomalies = state.get("anomalies", [])
    current_iters = state.get("iterations", 0)
    
    # Logic: Loop once to "refine" data
    if current_iters < 1:
        return {
            "iterations": current_iters + 1,
            "logs": ["Strategist needs more granular data. Requesting refinement..."]
        }

    search_query = f"{state['keyword']} trend {anomalies[0] if anomalies else 'breakout'}"
    search_results = google_search(search_query, num_results=3)
    search_signal = " ".join(search_results).lower()
    competition_is_high = "wikipedia.org" in search_signal or "forbes.com" in search_signal
    top_result = search_results[0] if search_results else "No result"

    if anomalies:
        if competition_is_high:
            strategy = (
                f"Breakout detected in {anomalies[0]}, but search indicates strong competition. "
                "Recommend targeted long-tail positioning before paid growth."
            )
        else:
            strategy = (
                f"Aggressive entry recommended following the {anomalies[0]} breakout. "
                "Focus on educational content and early-adopter acquisition."
            )
    else:
        strategy = (
            "No clear breakout detected. Recommend monitoring and building organic presence without heavy investment."
        )
        
    return {
        "strategy": strategy,
        "logs": [
            f"Strategist checked Google results for: {search_query}",
            f"Top result observed: {top_result}",
            "Finalized market entry strategy based on refined data",
        ]
    }

def verification(state: AgentState) -> dict:
    """Mocks using a search tool to check existing content for the trend."""
    time.sleep(DELAY_SECONDS)
    print("--- [Node: Verification] Verifying market saturation ---")
    # Mocking a search tool result
    verification_result = "Low competition detected. High authority sites haven't covered the December spike yet. Market is OPEN."
    
    return {
        "verification": verification_result,
        "logs": ["Verified niche availability via search mock"]
    }

# Router for strategist
def should_continue(state: AgentState) -> Literal["researcher", "verifier"]:
    # If strategy not set yet, it means we chose to loop
    if not state.get("strategy"):
        return "researcher"
    return "verifier"

# 3. Build the Graph
workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("researcher", trend_researcher)
workflow.add_node("detector", anomaly_detector)
workflow.add_node("strategist", market_strategist)
workflow.add_node("verifier", verification)

# Define edges
workflow.add_edge(START, "researcher")
workflow.add_edge("researcher", "detector")
workflow.add_edge("detector", "strategist")

# Conditional edge from strategist
workflow.add_conditional_edges(
    "strategist",
    should_continue,
    {
        "researcher": "researcher",
        "verifier": "verifier"
    }
)

workflow.add_edge("verifier", END)

# Compile the graph
app = workflow.compile()

def run_niche_agent(keyword: str):
    """Executes the niche discovery agent with the given keyword."""
    initial_input = {
        "keyword": keyword,
        "iterations": 0,
        "logs": ["Agent initialized"]
    }
    
    # Run the graph
    return app.invoke(initial_input)

# 4. Main Execution Block
if __name__ == "__main__":
    print("=== Niche Discovery Agent Starting ===\n")
    
    # Get keyword from command line argument if provided, otherwise prompt user
    if len(sys.argv) > 1:
        keyword = sys.argv[1]
    else:
        keyword = input("Enter the niche keyword to research: ")
    
    if not keyword.strip():
        print("Error: No keyword provided. Exiting.")
        sys.exit(1)
        
    final_state = run_niche_agent(keyword)
    
    print("\n=== Agent Results ===")
    print(f"Keyword: {final_state['keyword']}")
    print(f"Strategy: {final_state['strategy']}")
    print(f"Verification: {final_state['verification']}")
    print("\n--- Execution Logs ---")
    for log in final_state["logs"]:
        print(f"- {log}")
