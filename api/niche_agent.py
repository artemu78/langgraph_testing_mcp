import sys
import operator
from typing import Annotated, TypedDict, List, Dict, Literal
from langgraph.graph import StateGraph, START, END

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

def trend_researcher(state: AgentState) -> dict:
    """Mocks fetching historical data for a keyword."""
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
    print("--- [Node: Market Strategist] Developing strategy ---")
    anomalies = state.get("anomalies", [])
    current_iters = state.get("iterations", 0)
    
    # Logic: Loop once to "refine" data
    if current_iters < 1:
        return {
            "iterations": current_iters + 1,
            "logs": ["Strategist needs more granular data. Requesting refinement..."]
        }

    if anomalies:
        strategy = f"Aggressive entry recommended following the {anomalies[0]} breakout. Focus on educational content and early-adopter acquisition."
    else:
        strategy = "No clear breakout detected. Recommend monitoring and building organic presence without heavy investment."
        
    return {
        "strategy": strategy,
        "logs": ["Finalized market entry strategy based on refined data"]
    }

def verification(state: AgentState) -> dict:
    """Mocks using a search tool to check existing content for the trend."""
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
