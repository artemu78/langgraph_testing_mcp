# Niche Discovery Agent

This project implements an autonomous Niche Discovery Agent using LangGraph, exposed via a FastAPI backend, and presented through a React Vite frontend.

## Architecture

The core of the application is a LangGraph agent that performs trend research, anomaly detection, market strategy, and verification. The workflow is visualized below:

```mermaid
graph TD
    %% Styling
    classDef default fill:#f4f4f9,stroke:#333,stroke-width:2px,color:#000;
    classDef endpoint fill:#d4edda,stroke:#28a745,stroke-width:3px,color:#000;
    linkStyle default stroke:#d3d3d3,stroke-width:2px,color:#d3d3d3;

    %% Special Nodes
    START(((START))):::endpoint
    END(((END))):::endpoint
    
    %% Action Nodes
    researcher["<b>trend_researcher</b><br/>(Fetches historical data)"]
    detector["<b>anomaly_detector</b><br/>(Identifies breakout spikes)"]
    strategist["<b>market_strategist</b><br/>(Develops entry strategy)"]
    verifier["<b>verification</b><br/>(Checks market saturation)"]

    %% Edges (Linear Flow)
    START --> researcher
    researcher -->|Updates: trend_data| detector
    detector -->|Updates: anomalies| strategist
    strategist -->|Updates: strategy| verifier
    strategist -->|Loop: Refine| researcher
    verifier -->|Updates: verification| END
```

- The **FastAPI backend** (in the `api/` directory) wraps the LangGraph agent, providing an API endpoint that streams real-time updates using Server-Sent Events (SSE).
- The **React Vite frontend** (in the `frontend/` directory) consumes these SSE streams to display the agent's progress, logs, and final results, including an interactive Mermaid graph visualization.

## Setup Instructions

Follow these steps to set up and run the Niche Discovery Agent:

### Prerequisites

- Python 3.9+
- Node.js 18+
- npm
- pip

### 1. Backend Setup (FastAPI)

Navigate to the `api` directory and install the Python dependencies:

```bash
cd api
pip install -r requirements.txt
```

If `requirements.txt` does not exist, you can create it with the following:

```bash
pip freeze > requirements.txt
```

Then, navigate back to the project root.

### 2. Frontend Setup (React Vite)

Navigate to the `frontend` directory and install the Node.js dependencies:

```bash
cd frontend
npm install
```

Then, navigate back to the project root.

### 3. Running the Application

To run both the backend and frontend concurrently, open two separate terminal windows:

#### Terminal 1: Start Backend

From the project root, start the FastAPI server:

```bash
export PYTHONPATH=$PYTHONPATH:. && uvicorn api.main:app --host 0.0.0.0 --port 8000
```

#### Terminal 2: Start Frontend

From the project root, start the React development server:

```bash
cd frontend
npm run dev -- --host 0.0.0.0
```

### 4. Accessing the UI

Once both servers are running, open your web browser and navigate to:

[http://localhost:5173](http://localhost:5173)

You can then enter a niche keyword in the input box and observe the agent's execution, logs, and results in real-time.
