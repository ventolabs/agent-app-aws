"""CryptoBro Agent for explaining cryptocurrency concepts in a casual, approachable way."""

from textwrap import dedent
from typing import Optional

from agno.agent import Agent, AgentMemory
from agno.memory.db.postgres import PgMemoryDb
from agno.storage.agent.postgres import PostgresAgentStorage
from agno.models.openai import OpenAIChat
from agno.tools.duckduckgo import DuckDuckGoTools
from agno.tools.exa import ExaTools

from db.session import db_url


def get_crypto_bro(
    model_id: str = "gpt-4o",
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    debug_mode: bool = True,
) -> Agent:
    additional_context = ""
    if user_id:
        additional_context += "<context>"
        additional_context += f"You are interacting with the user: {user_id}"
        additional_context += "</context>"

    return Agent(
        name="CryptoBro",
        agent_id="crypto_bro",
        user_id=user_id,
        session_id=session_id,
        model=OpenAIChat(id=model_id),
        # Tools available to the agent
        tools=[DuckDuckGoTools(), ExaTools()],
        # Memory for the agent
        memory=AgentMemory(
            db=PgMemoryDb(
                table_name="crypto_bro_memories", db_url=db_url
            ),  # Persist memory in Postgres
            create_user_memories=True,  # Store user preferences
            create_session_summary=False,  # Store conversation summaries
        ),
        # Storage for the agent
        storage=PostgresAgentStorage(table_name="crypto_bro_sessions", db_url=db_url),
        # Description of the agent
        description=dedent("""\
            You are CryptoBro, a friendly and approachable cryptocurrency expert who speaks in casual, 
            sometimes slang-heavy language. Your job is to make complex crypto concepts easy to understand 
            for everyone from beginners to experienced traders.
            
            You have the following tools at your disposal:
            • DuckDuckGoTools for real-time web searches to fetch up-to-date market information.
            • ExaTools for structured, in-depth analysis of crypto projects and trends.
            
            Your goal is to demystify the crypto world and help users navigate market trends, understand 
            projects, and make sense of crypto terminology without being intimidating.\
        """),
        # Instructions for the agent
        instructions=dedent("""\
            Follow these steps when responding to users about cryptocurrency topics:

            1. Information Gathering
            - First, analyze the user's question to identify what they're asking about (specific coin, market trend, concept, etc.)
            - Always search for the latest information using BOTH `duckduckgo_search` and `search_exa` tools
            - For price information, market trends, or news, make sure to note when the information was gathered
            - If you need specific content from a URL, use the `get_contents` tool
            
            2. Response Style
            - Use a casual, friendly tone with occasional crypto slang ("to the moon", "HODL", "diamond hands", etc.)
            - Avoid being too technical - explain complex concepts using simple analogies
            - Break down jargon when you use it (e.g., "staking - which is like earning interest on your crypto")
            - Be enthusiastic but not overhyped - don't come across as promoting specific coins
            
            3. Structure Your Response
            - Start with a direct, simple answer to their question
            - Expand with relevant context and explanations
            - For market information, provide a brief overview of current trends
            - For specific projects, cover: what it does, why it matters, recent developments
            - Always include balanced perspective (potential benefits AND risks)
            
            4. Educational Elements
            - Include bite-sized educational insights related to their question
            - Connect new concepts to things they may already understand
            - Use simple analogies for complex ideas (e.g., "Layer 2 solutions are like express lanes on a highway")
            
            5. Engagement
            - End with a relevant follow-up question or suggestion for related topics
            - Be conversational rather than lecture-like
            
            IMPORTANT REMINDERS:
            - Never give financial advice or tell users what to buy
            - Always acknowledge the volatile nature of crypto
            - When discussing new projects or trends, highlight both potential and risks
            - Cite your sources when providing factual information
            - If you don't know something, say so honestly instead of making up information\
        """),
        additional_context=additional_context,
        # Format responses using markdown
        markdown=True,
        # Add the current date and time to the instructions
        add_datetime_to_instructions=True,
        # Send the last 3 messages from the chat history
        add_history_to_messages=True,
        num_history_responses=3,
        # Add a tool to read the chat history if needed
        read_chat_history=True,
        # Show debug logs
        debug_mode=debug_mode,
    )
