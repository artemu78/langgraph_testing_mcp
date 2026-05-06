# Niche Agent Workflow Diagram

This diagram visualizes the LangGraph workflow defined in `niche_agent_mock.py`. It shows the sequence of nodes and the primary actions each node performs.

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': { 'primaryColor': '#000000', 'primaryTextColor': '#DDDDDD', 'primaryBorderColor': '#777777', 'lineColor': '#AAAAAA', 'edgeLabelBackground':'#000000', 'tertiaryTextColor': '#FFFFFF' }}}%%
graph TD
    %% Styling
    classDef darkNode fill:#000000,stroke:#777777,stroke-width:2px,color:#DDDDDD;
    linkStyle default stroke:#AAAAAA,stroke-width:2px,labelColor:#FFFFFF;

    %% Nodes
    START(((START))):::darkNode
    END(((END))):::darkNode
    researcher["<b>trend_researcher</b><br/>(Fetches historical data)"]:::darkNode
    detector["<b>anomaly_detector</b><br/>(Identifies breakout spikes)"]:::darkNode
    strategist["<b>market_strategist</b><br/>(Develops entry strategy)"]:::darkNode
    verifier["<b>verification</b><br/>(Checks market saturation)"]:::darkNode

    %% Edges
    START --> researcher
    researcher -->|Updates: trend_data| detector
    detector -->|Updates: anomalies| strategist
    strategist -->|Updates: strategy| verifier
    strategist -->|Loop: Refine| researcher
    verifier -->|Updates: verification| END
```
