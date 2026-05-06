#!/bin/bash

python -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn langgraph
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000