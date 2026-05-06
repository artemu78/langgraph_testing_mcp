import sys
import time
import operator
import json
import urllib.parse
import urllib.request
import os
import re
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
    # Strategist's routing decision
    should_research_again: bool
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
        "should_research_again": False,
        "logs": [f"Fetched trend data for {state['keyword']}{iter_info}"]
    }


def _load_env_value_from_api_dotenv(key: str) -> str:
    """Reads api/.env and returns the requested key if present."""
    dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(dotenv_path):
        return ""

    try:
        with open(dotenv_path, "r", encoding="utf-8") as file:
            for raw_line in file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                env_key, env_value = line.split("=", 1)
                if env_key.strip() != key:
                    continue
                cleaned = env_value.strip().strip('"').strip("'")
                return cleaned
    except OSError:
        return ""
    return ""


def _get_gemini_api_key() -> str:
    return os.getenv("GEMINI_API_KEY") or _load_env_value_from_api_dotenv("GEMINI_API_KEY")


def _gemini_json_request(url: str, payload: dict, timeout: int = 12) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _list_gemini_models(api_key: str) -> List[dict]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    with urllib.request.urlopen(url, timeout=8) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("models", [])


def _pick_active_flash_model(models: List[dict]) -> str:
    """Selects Gemini 2.5 Flash if available and not explicitly deprecated."""
    if not models:
        return ""

    preferred_candidates = [
        "models/gemini-2.5-flash",
        "models/gemini-2.5-flash-latest",
        "models/gemini-2.5-flash-preview",
    ]

    for candidate in preferred_candidates:
        for model in models:
            name = model.get("name", "")
            model_lower = name.lower()
            description_lower = model.get("description", "").lower()
            methods = model.get("supportedGenerationMethods", [])
            if (
                name == candidate
                and "generatecontent" in [m.lower() for m in methods]
                and "deprecat" not in model_lower
                and "deprecat" not in description_lower
            ):
                return name
    return ""


def _extract_json_object(text: str) -> dict:
    """Extracts first JSON object from text if model wraps output in markdown."""
    if not text:
        return {}
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, re.DOTALL)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}


def _gemini_should_research_again(state: AgentState) -> dict:
    """Uses Gemini 2.5 Flash to decide whether to loop back to trend research."""
    api_key = _get_gemini_api_key()
    if not api_key:
        return {
            "should_research_again": state.get("iterations", 0) < 1,
            "reason": "GEMINI_API_KEY not found in env or api/.env, using fallback rule.",
            "model": "",
        }

    try:
        models = _list_gemini_models(api_key)
        model_name = _pick_active_flash_model(models)
        if not model_name:
            return {
                "should_research_again": state.get("iterations", 0) < 1,
                "reason": "Gemini 2.5 Flash model not available or appears deprecated. Using fallback rule.",
                "model": "",
            }

        prompt = (
            "You are a market research strategist router.\n"
            "Decide if trend research should run again to gather more data.\n"
            "Respond with strict JSON only and no markdown:\n"
            '{"should_research_again": boolean, "reason": "short reason"}\n\n'
            f"Keyword: {state.get('keyword', '')}\n"
            f"Current iterations: {state.get('iterations', 0)}\n"
            f"Detected anomalies: {state.get('anomalies', [])}\n"
            f"Trend data: {state.get('trend_data', {})}\n"
            "Decision guidance:\n"
            "- Prefer one refinement pass when confidence is low.\n"
            "- Do not request refinement if enough data exists for a concrete strategy.\n"
            "- Never request refinement when iterations >= 2.\n"
        )

        request_body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={api_key}"
        response = _gemini_json_request(url, request_body)
        candidate = (response.get("candidates") or [{}])[0]
        parts = candidate.get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts)
        decision = _extract_json_object(text)
        should_again = bool(decision.get("should_research_again", False))
        reason = str(decision.get("reason", "No reason returned by Gemini."))

        # Safety cap against infinite loops
        if state.get("iterations", 0) >= 2:
            should_again = False
            reason = "Iteration cap reached; forcing strategy synthesis."

        return {"should_research_again": should_again, "reason": reason, "model": model_name}
    except Exception as exc:
        return {
            "should_research_again": state.get("iterations", 0) < 1,
            "reason": f"Gemini decision call failed: {exc}. Using fallback rule.",
            "model": "",
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
    
    decision = _gemini_should_research_again(state)
    should_research_again = decision["should_research_again"]
    decision_reason = decision["reason"]
    used_model = decision["model"] or "fallback-rule"

    if should_research_again:
        return {
            "iterations": current_iters + 1,
            "strategy": "",
            "should_research_again": True,
            "logs": [
                f"Strategist decision via {used_model}: request another trend research round.",
                f"Decision reason: {decision_reason}",
            ],
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
        "should_research_again": False,
        "logs": [
            f"Strategist decision via {used_model}: proceed without another research round.",
            f"Decision reason: {decision_reason}",
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
    if state.get("should_research_again"):
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
        "should_research_again": False,
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
