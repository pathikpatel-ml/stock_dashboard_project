"""
Agentic paper-trading simulator (Simulator tab).

Two independent virtual portfolios (one per strategy -- "v20" and "turtle"), each traded by an
LLM agent (LangGraph + OpenRouter, see modules/simulator/agent.py) that decides entry/exit
timing and position size on top of the app's real V20/Turtle signals. The agent runs offline,
once daily, via generate_simulator_decisions.py under GitHub Actions -- never inline in a Dash
callback (this app runs on a single sync gunicorn worker; LLM+web-search latency must never
share that worker with live user traffic). The live Dash tab (modules/simulator/layout.py +
callbacks.py) only displays what the batch job already wrote to Postgres, plus lets the user
change their own config (starting balance, position-size cap, active on/off, reset).

modules/simulator/store.py    -- Supabase REST helpers (mirrors modules/auth/user_store.py),
                                  used by BOTH the live app and the batch script.
modules/simulator/candidates.py -- pulls today's buy/sell candidate list per strategy from the
                                  existing V20/Turtle signal tables.
modules/simulator/tools.py    -- the agent's free web-search tool (ddgs, no API key).
modules/simulator/agent.py    -- the LangGraph ReAct agent that turns one candidate + portfolio
                                  state into a BUY/SELL/SKIP decision.
modules/simulator/executor.py -- enforces the hard max_position_pct cap and records the
                                  resulting trade via store.py.
"""
