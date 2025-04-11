from os import getenv

from agno.playground import Playground

from agents.sage import get_sage
from agents.scholar import get_scholar
from agents.crypto.waves import get_waves_liquidity_manager
from workspace.dev_resources import dev_fastapi

######################################################
## Router for the Playground Interface
######################################################

sage_agent = get_sage(debug_mode=True)
scholar_agent = get_scholar(debug_mode=True)
waves_liquidity_manager = get_waves_liquidity_manager(debug_mode=True)

# Create a playground instance
playground = Playground(agents=[sage_agent, scholar_agent, waves_liquidity_manager])

# Register the endpoint where playground routes are served with agno.com
if getenv("RUNTIME_ENV") == "dev":
    playground.create_endpoint(f"http://localhost:{dev_fastapi.host_port}")

playground_router = playground.get_async_router()
