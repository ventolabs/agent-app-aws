# agent-app-aws/ui/pages/3_Waves_Liquidity_Manager.py

import asyncio

import nest_asyncio
import streamlit as st
from agno.agent import Agent
from agno.tools.streamlit.components import check_password
from agno.utils.log import logger

from agents.crypto import get_waves_liquidity_manager
from ui.css import CUSTOM_CSS
from ui.utils import (
    about_agno,
    add_message,
    display_tool_calls,
    initialize_agent_session_state,
    selected_model,
    session_selector,
    utilities_widget,
)

nest_asyncio.apply()

st.set_page_config(
    page_title="Waves Liquidity Manager",
    page_icon=":ocean:",
    layout="wide",
)
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
agent_name = "waves_liquidity_manager"


async def header():
    st.markdown("<h1 class='heading'>Waves Liquidity Manager</h1>", unsafe_allow_html=True)
    st.markdown(
        "<p class='subheading'>An agent that helps optimize your USDT liquidity across Puzzle Lend pools on the Waves blockchain.</p>",
        unsafe_allow_html=True,
    )


async def crypto_dashboard():
    """Display a simple dashboard with key information about USDT pools and current allocations."""
    st.sidebar.markdown("### USDT Pools Dashboard")
    
    with st.sidebar.expander("Your USDT Balance", expanded=True):
        st.markdown("Loading wallet balances...")
        
    with st.sidebar.expander("Current Staked Positions", expanded=True):
        st.markdown("Loading staked positions...")
        
    with st.sidebar.expander("Available Puzzle Lend Pools", expanded=True):
        st.markdown("Loading pool information...")


async def body() -> None:
    ####################################################################
    # Initialize User and Session State
    ####################################################################
    user_id = st.sidebar.text_input(":technologist: Username", value="Investor")

    ####################################################################
    # Model selector
    ####################################################################
    model_id = await selected_model()

    ####################################################################
    # Display the dashboard
    ####################################################################
    await crypto_dashboard()

    ####################################################################
    # Initialize Agent
    ####################################################################
    waves_manager: Agent
    if (
        agent_name not in st.session_state
        or st.session_state[agent_name]["agent"] is None
        or st.session_state.get("selected_model") != model_id
    ):
        logger.info("---*--- Creating Waves Liquidity Manager Agent ---*---")
        waves_manager = get_waves_liquidity_manager(user_id=user_id, model_id=model_id)
        st.session_state[agent_name]["agent"] = waves_manager
        st.session_state["selected_model"] = model_id
    else:
        waves_manager = st.session_state[agent_name]["agent"]

    ####################################################################
    # Load Agent Session from the database
    ####################################################################
    try:
        st.session_state[agent_name]["session_id"] = waves_manager.load_session()
    except Exception:
        st.warning("Could not create Agent session, is the database running?")
        return

    ####################################################################
    # Load agent runs (i.e. chat history) from memory if messages is empty
    ####################################################################
    if waves_manager.memory:
        agent_runs = waves_manager.memory.runs
        if len(agent_runs) > 0:
            # If there are runs, load the messages
            logger.debug("Loading run history")
            # Clear existing messages
            st.session_state[agent_name]["messages"] = []
            # Loop through the runs and add the messages to the messages list
            for agent_run in agent_runs:
                if agent_run.message is not None:
                    await add_message(agent_name, agent_run.message.role, str(agent_run.message.content))
                if agent_run.response is not None:
                    await add_message(
                        agent_name, "assistant", str(agent_run.response.content), agent_run.response.tools
                    )

    ####################################################################
    # Get user input
    ####################################################################
    if prompt := st.chat_input("💰 How can I help optimize your USDT liquidity?"):
        await add_message(agent_name, "user", prompt)

    ####################################################################
    # Show example inputs
    ####################################################################
    with st.sidebar:
        st.markdown("#### :thinking_face: Try asking")
        if st.button("What's the highest APY pool?"):
            await add_message(
                agent_name,
                "user",
                "What's the highest APY pool for USDT right now?",
            )
        if st.button("Stake my USDT"):
            await add_message(
                agent_name,
                "user",
                "I want to stake my USDT in the highest yield pool.",
            )
        if st.button("Show my staked positions"):
            await add_message(
                agent_name,
                "user",
                "Show me all my current staked positions in Puzzle Lend pools.",
            )
        if st.button("Should I rebalance?"):
            await add_message(
                agent_name,
                "user",
                "Check if I should rebalance my current staked USDT for better returns.",
            )

    ####################################################################
    # Display agent messages
    ####################################################################
    for message in st.session_state[agent_name]["messages"]:
        if message["role"] in ["user", "assistant"]:
            _content = message["content"]
            if _content is not None:
                with st.chat_message(message["role"]):
                    # Display tool calls if they exist in the message
                    if "tool_calls" in message and message["tool_calls"]:
                        display_tool_calls(st.empty(), message["tool_calls"])
                    st.markdown(_content)

    ####################################################################
    # Generate response for user message
    ####################################################################
    last_message = st.session_state[agent_name]["messages"][-1] if st.session_state[agent_name]["messages"] else None
    if last_message and last_message.get("role") == "user":
        user_message = last_message["content"]
        logger.info(f"Responding to message: {user_message}")
        with st.chat_message("assistant"):
            # Create container for tool calls
            tool_calls_container = st.empty()
            resp_container = st.empty()
            with st.spinner(":thinking_face: Analyzing Waves blockchain data..."):
                response = ""
                try:
                    # Run the agent and stream the response
                    run_response = await waves_manager.arun(user_message, stream=True)
                    async for resp_chunk in run_response:
                        # Display tool calls if available
                        if resp_chunk.tools and len(resp_chunk.tools) > 0:
                            display_tool_calls(tool_calls_container, resp_chunk.tools)

                        # Display response
                        if resp_chunk.content is not None:
                            response += resp_chunk.content
                            resp_container.markdown(response)

                    # Add the response to the messages
                    if waves_manager.run_response is not None:
                        await add_message(agent_name, "assistant", response, waves_manager.run_response.tools)
                    else:
                        await add_message(agent_name, "assistant", response)
                except Exception as e:
                    logger.error(f"Error during agent run: {str(e)}", exc_info=True)
                    error_message = f"Sorry, I encountered an error: {str(e)}"
                    await add_message(agent_name, "assistant", error_message)
                    st.error(error_message)

    ####################################################################
    # Session selector
    ####################################################################
    await session_selector(agent_name, waves_manager, get_waves_liquidity_manager, user_id, model_id)

    ####################################################################
    # About section
    ####################################################################
    await utilities_widget(agent_name, waves_manager)


async def main():
    await initialize_agent_session_state(agent_name)
    await header()
    await body()
    await about_agno()


if __name__ == "__main__":
    if check_password():
        asyncio.run(main())