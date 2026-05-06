import sys
import time
import operator
import json
import urllib.parse
import urllib.request
import os
import re
import sqlite3
import random
from datetime import datetime, timezone
from typing import Annotated, TypedDict, List, Dict, Literal
from langgraph.graph import StateGraph, START, END
from pytrends.request import TrendReq

# Delay applied at the start of each node execution.
DELAY_SECONDS = 0.5
ERROR_LOG_PATH = os.path.join(os.path.dirname(__file__), "logs", "agent_errors.log")
DB_PATH = os.path.join(os.path.dirname(__file__), "logs", "node_findings.db")
TREND_RETRY_STATUS_CODES = {403, 429}
TREND_MAX_ATTEMPTS = 4
TREND_BASE_BACKOFF_SECONDS = 1.0

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
    # Signals Trends fetch failed due rate-limit/access errors.
    trend_fetch_failed: bool
    # Using Annotated with operator.add to accumulate logs instead of overwriting
    logs: Annotated[List[str], operator.add]

# 2. Define the Nodes with Mocked Logic

def _append_error_log(source: str, message: str, context: Dict[str, str] | None = None) -> None:
    """Appends structured error lines to a dedicated on-disk log file."""
    timestamp = datetime.now(timezone.utc).isoformat()
    safe_context = context or {}
    context_line = ", ".join(f"{k}={v}" for k, v in safe_context.items()) or "none"
    log_entry = f"[{timestamp}] source={source} message={message} context={context_line}\n"

    try:
        os.makedirs(os.path.dirname(ERROR_LOG_PATH), exist_ok=True)
        with open(ERROR_LOG_PATH, "a", encoding="utf-8") as log_file:
            log_file.write(log_entry)
    except OSError:
        # Never break agent execution because of logging failures.
        pass


def _init_findings_db() -> None:
    """Creates the SQLite table used for node findings if missing."""
    try:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS node_findings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    keyword TEXT NOT NULL,
                    node_name TEXT NOT NULL,
                    request_payload TEXT NOT NULL,
                    result_payload TEXT NOT NULL
                )
                """
            )
            conn.commit()
    except sqlite3.Error as exc:
        _append_error_log(
            source="node_findings_db_init",
            message=str(exc),
            context={"db_path": DB_PATH},
        )


def _persist_node_finding(
    node_name: str,
    keyword: str,
    request_payload: Dict[str, object],
    result_payload: Dict[str, object],
) -> None:
    """Writes one node finding into SQLite with timestamp, request, and result."""
    _init_findings_db()
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO node_findings (
                    created_at, keyword, node_name, request_payload, result_payload
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    keyword,
                    node_name,
                    json.dumps(request_payload, ensure_ascii=True),
                    json.dumps(result_payload, ensure_ascii=True),
                ),
            )
            conn.commit()
    except sqlite3.Error as exc:
        _append_error_log(
            source="node_findings_db_write",
            message=str(exc),
            context={"node_name": node_name, "keyword": keyword},
        )


def google_search(query: str, num_results: int = 5) -> List[str]:
    """Runs Google Custom Search API and returns top result snippets.

    Requires:
    - GOOGLE_API_KEY
    - GOOGLE_CSE_ID
    """
    api_key = os.getenv("GOOGLE_API_KEY") or _load_env_value_from_api_dotenv("GOOGLE_API_KEY")
    cse_id = os.getenv("GOOGLE_CSE_ID") or _load_env_value_from_api_dotenv("GOOGLE_CSE_ID")

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
        _append_error_log(
            source="google_search",
            message=str(exc),
            context={"query": query, "url": url},
        )
        return [f"Search failed: {exc}"]

    items = payload.get("items", [])
    if not items:
        return ["No search results found for this query."]

    return [
        f"{item.get('title', 'Untitled')} | {item.get('link', 'No link')}"
        for item in items
    ]

def trend_researcher(state: AgentState) -> dict:
    """Prepares a research round before live trend collection."""
    time.sleep(DELAY_SECONDS)
    iter_info = f" (Round {state.get('iterations', 0) + 1})"
    print(f"--- [Node: Trend Researcher] Researching: {state['keyword']}{iter_info} ---")
    result = {
        "trend_data": {},
        "should_research_again": False,
        "trend_fetch_failed": False,
        "logs": [f"Prepared live trend lookup for {state['keyword']}{iter_info}"]
    }
    _persist_node_finding(
        node_name="trend_researcher",
        keyword=state.get("keyword", ""),
        request_payload={
            "keyword": state.get("keyword", ""),
            "iterations": state.get("iterations", 0),
        },
        result_payload=result,
    )
    return result


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
        _append_error_log(
            source="gemini_router",
            message=str(exc),
            context={
                "keyword": str(state.get("keyword", "")),
                "iterations": str(state.get("iterations", 0)),
            },
        )
        return {
            "should_research_again": state.get("iterations", 0) < 1,
            "reason": f"Gemini decision call failed: {exc}. Using fallback rule.",
            "model": "",
        }


def _extract_http_status_code(exc: Exception) -> int | None:
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        return code

    match = re.search(r"code\s+(\d{3})", str(exc), flags=re.IGNORECASE)
    if not match:
        return None

    try:
        return int(match.group(1))
    except ValueError:
        return None


def _fetch_interest_over_time(keyword: str, timeframe: str):
    """Fetches Google Trends data with backoff for temporary access limits."""
    last_exc: Exception | None = None

    for attempt in range(1, TREND_MAX_ATTEMPTS + 1):
        pytrends = TrendReq(hl="en-US", tz=0)
        try:
            pytrends.build_payload([keyword], timeframe=timeframe)
            return pytrends.interest_over_time(), attempt
        except Exception as exc:
            last_exc = exc
            status_code = _extract_http_status_code(exc)
            can_retry = status_code in TREND_RETRY_STATUS_CODES

            if not can_retry or attempt >= TREND_MAX_ATTEMPTS:
                raise

            wait_seconds = TREND_BASE_BACKOFF_SECONDS * (2 ** (attempt - 1)) + random.uniform(0.0, 0.4)
            _append_error_log(
                source="anomaly_detector_retry",
                message=str(exc),
                context={
                    "keyword": keyword,
                    "status_code": str(status_code),
                    "attempt": str(attempt),
                    "next_wait_seconds": f"{wait_seconds:.2f}",
                },
            )
            time.sleep(wait_seconds)

    if last_exc:
        raise last_exc
    raise RuntimeError("Google Trends fetch failed without exception details.")

def anomaly_detector(state: AgentState) -> dict:
    """Fetches Google Trends data and identifies breakout spikes."""
    time.sleep(DELAY_SECONDS)
    print("--- [Node: Anomaly Detector] Fetching Google Trends and analyzing spikes ---")

    keyword = state.get("keyword", "").strip()
    if not keyword:
        result = {
            "anomalies": [],
            "trend_data": {},
            "logs": ["Anomaly detection skipped: missing keyword."],
        }
        _persist_node_finding(
            node_name="anomaly_detector",
            keyword="",
            request_payload={"keyword": keyword, "trend_data": state.get("trend_data", {})},
            result_payload=result,
        )
        return result

    try:
        interest_df, attempts_used = _fetch_interest_over_time(keyword, "today 12-m")
    except Exception as exc:
        _append_error_log(
            source="anomaly_detector",
            message=str(exc),
            context={"keyword": keyword},
        )
        result = {
            "anomalies": [],
            "trend_data": {},
            "trend_fetch_failed": True,
            "logs": [f"Google Trends fetch failed for '{keyword}': {exc}"],
        }
        _persist_node_finding(
            node_name="anomaly_detector",
            keyword=keyword,
            request_payload={"keyword": keyword, "timeframe": "today 12-m"},
            result_payload=result,
        )
        return result

    if interest_df.empty or keyword not in interest_df.columns:
        result = {
            "anomalies": [],
            "trend_data": {},
            "trend_fetch_failed": False,
            "logs": [f"No Google Trends data available for '{keyword}' in the last 12 months."],
        }
        _persist_node_finding(
            node_name="anomaly_detector",
            keyword=keyword,
            request_payload={"keyword": keyword, "timeframe": "today 12-m"},
            result_payload=result,
        )
        return result

    values = interest_df[keyword].astype(float)
    trend_data = {idx.strftime("%Y-%m-%d"): float(val) for idx, val in values.items()}

    # Mark breakout points at or above one stddev above mean, with a floor to avoid tiny fluctuations.
    mean_value = float(values.mean())
    std_value = float(values.std()) if len(values) > 1 else 0.0
    threshold = max(30.0, mean_value + std_value)
    anomalies = [
        idx.strftime("%Y-%m-%d")
        for idx, val in values.items()
        if float(val) >= threshold
    ]

    status = (
        f"Fetched {len(values)} Google Trends points in {attempts_used} attempt(s). Breakout threshold={threshold:.2f}. "
        f"Detected spikes at: {anomalies}"
        if anomalies
        else f"Fetched {len(values)} Google Trends points in {attempts_used} attempt(s). No spikes above threshold={threshold:.2f}."
    )
    result = {
        "anomalies": anomalies,
        "trend_data": trend_data,
        "trend_fetch_failed": False,
        "logs": [status],
    }
    _persist_node_finding(
        node_name="anomaly_detector",
        keyword=keyword,
        request_payload={"keyword": keyword, "timeframe": "today 12-m"},
        result_payload=result,
    )
    return result

def market_strategist(state: AgentState) -> dict:
    """Mocks analyzing spikes and suggesting entry points."""
    time.sleep(DELAY_SECONDS)
    print("--- [Node: Market Strategist] Developing strategy ---")
    anomalies = state.get("anomalies", [])
    current_iters = state.get("iterations", 0)
    
    if state.get("trend_fetch_failed", False):
        should_research_again = False
        decision_reason = "Google Trends fetch failed; strategy generation is marked inconclusive."
        used_model = "local-safety-rule"
    else:
        decision = _gemini_should_research_again(state)
        should_research_again = decision["should_research_again"]
        decision_reason = decision["reason"]
        used_model = decision["model"] or "fallback-rule"

    if should_research_again:
        result = {
            "iterations": current_iters + 1,
            "strategy": "",
            "should_research_again": True,
            "logs": [
                f"Strategist decision via {used_model}: request another trend research round.",
                f"Decision reason: {decision_reason}",
            ],
        }
        _persist_node_finding(
            node_name="market_strategist",
            keyword=state.get("keyword", ""),
            request_payload={
                "keyword": state.get("keyword", ""),
                "anomalies": anomalies,
                "iterations": current_iters,
            },
            result_payload=result,
        )
        return result

    if state.get("trend_fetch_failed", False):
        result = {
            "strategy": (
                "Inconclusive: unable to generate a reliable market-entry strategy because "
                "Google Trends data could not be fetched (rate-limit/access error)."
            ),
            "should_research_again": False,
            "logs": [
                "Strategist hard stop: core trend signal unavailable.",
                f"Decision reason: {decision_reason}",
                "Returned inconclusive strategy to avoid false confidence.",
            ],
        }
        _persist_node_finding(
            node_name="market_strategist",
            keyword=state.get("keyword", ""),
            request_payload={
                "keyword": state.get("keyword", ""),
                "anomalies": anomalies,
                "iterations": current_iters,
                "trend_fetch_failed": True,
            },
            result_payload=result,
        )
        return result

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
        
    result = {
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
    _persist_node_finding(
        node_name="market_strategist",
        keyword=state.get("keyword", ""),
        request_payload={
            "keyword": state.get("keyword", ""),
            "anomalies": anomalies,
            "iterations": current_iters,
            "search_query": search_query,
        },
        result_payload=result,
    )
    return result

def verification(state: AgentState) -> dict:
    """Verifies market saturation using live Google Custom Search signals."""
    time.sleep(DELAY_SECONDS)
    print("--- [Node: Verification] Verifying market saturation ---")
    keyword = state.get("keyword", "").strip()
    anomalies = state.get("anomalies", [])
    trend_fetch_failed = state.get("trend_fetch_failed", False)

    if trend_fetch_failed:
        verification_result = (
            "Verification uncertain: Google Trends fetch failed (rate-limit/access issue). "
            "Treat market opportunity assessment as inconclusive until trends data is available."
        )
        verification_logs = ["Verification downgraded because trend fetch failed upstream."]
    else:
        search_query = f"{keyword} trend {anomalies[0] if anomalies else 'breakout'}"
        search_results = google_search(search_query, num_results=5)
        search_signal = " ".join(search_results).lower()
        authority_hits = sum(
            1 for domain in ["wikipedia.org", "forbes.com", "techcrunch.com", "nytimes.com"]
            if domain in search_signal
        )

        if any(msg.startswith("Search unavailable:") or msg.startswith("Search failed:") for msg in search_results):
            verification_result = (
                "Verification uncertain: live search is unavailable, so competition level cannot be trusted."
            )
        elif authority_hits >= 2:
            verification_result = (
                "Competition appears HIGH: multiple high-authority sources already cover this trend."
            )
        elif authority_hits == 1:
            verification_result = (
                "Competition appears MEDIUM: at least one high-authority source is already covering this trend."
            )
        else:
            verification_result = (
                "Competition appears LOW from current search results; niche may still be open."
            )

        verification_logs = [
            f"Verification query: {search_query}",
            f"Verification top result: {search_results[0] if search_results else 'No result'}",
            f"Authority-site hits in sampled results: {authority_hits}",
        ]

    result = {
        "verification": verification_result,
        "logs": verification_logs,
    }
    _persist_node_finding(
        node_name="verification",
        keyword=state.get("keyword", ""),
        request_payload={
            "keyword": state.get("keyword", ""),
            "anomalies": anomalies,
            "strategy": state.get("strategy", ""),
            "trend_fetch_failed": trend_fetch_failed,
        },
        result_payload=result,
    )
    return result

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
        "trend_fetch_failed": False,
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
