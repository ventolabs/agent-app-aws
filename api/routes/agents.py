from enum import Enum
from typing import AsyncGenerator, List, Optional

from agno.agent import Agent
from agno.storage.agent.postgres import PostgresAgentStorage
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agents.operator import AgentType, get_agent, get_available_agents
from utils.log import logger
from agents.crypto import CryptoQuestionsOutput, suggest_crypto_questions_with_cache

from db.session import db_url

######################################################
## Router for Serving Agents
######################################################

agents_router = APIRouter(prefix="/agents", tags=["Agents"])


class Model(str, Enum):
    gpt_4o = "gpt-4o"
    o3_mini = "o3-mini"


@agents_router.get("", response_model=List[str])
async def list_agents():
    """
    GET /agents

    Returns a list of all available agent IDs.

    Returns:
        List[str]: List of agent identifiers
    """
    return get_available_agents()


async def chat_response_streamer(agent: Agent, message: str) -> AsyncGenerator:
    """
    Stream agent responses chunk by chunk.

    Args:
        agent: The agent instance to interact with
        message: User message to process

    Yields:
        Text chunks from the agent response
    """
    run_response = await agent.arun(message, stream=True)
    async for chunk in run_response:
        # chunk.content only contains the text response from the Agent.
        # For advanced use cases, we should yield the entire chunk
        # that contains the tool calls and intermediate steps.
        yield chunk.content


class RunRequest(BaseModel):
    """Request model for an running an agent"""

    message: str
    stream: bool = True
    model: Model = Model.gpt_4o
    user_id: Optional[str] = None
    session_id: Optional[str] = None


@agents_router.post("/{agent_id}/runs", status_code=status.HTTP_200_OK)
async def run_agent(agent_id: AgentType, body: RunRequest):
    """
    POST /agents/{agent_id}/run

    Sends a message to a specific agent and returns the response.

    Args:
        agent_id: The ID of the agent to interact with
        body: Request parameters including the message

    Returns:
        Either a streaming response or the complete agent response
    """
    logger.debug(f"RunRequest: {body}")

    try:
        agent: Agent = get_agent(
            model_id=body.model.value,
            agent_id=agent_id,
            user_id=body.user_id,
            session_id=body.session_id,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent not found: {str(e)}")

    if body.stream:
        return StreamingResponse(
            chat_response_streamer(agent, body.message),
            media_type="text/event-stream",
        )
    else:
        response = await agent.arun(body.message, stream=False)
        # response.content only contains the text response from the Agent.
        # For advanced use cases, we should yield the entire response
        # that contains the tool calls and intermediate steps.
        return response.content


class MessageHistoryRequest(BaseModel):
    """Request model for retrieving message history"""
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    limit: Optional[int] = 50
    model: Model = Model.gpt_4o


@agents_router.post("/{agent_id}/history", status_code=status.HTTP_200_OK)
async def get_agent_history(agent_id: AgentType, body: MessageHistoryRequest):
    """
    POST /agents/{agent_id}/history
    
    Retrieves message history for a specific agent session by accessing
    stored sessions directly from PostgresAgentStorage.
    
    Args:
        agent_id: The ID of the agent
        body: Request parameters including user_id and session_id
        
    Returns:
        List of message history objects containing role, content and timestamp
    """
    logger.debug(f"MessageHistoryRequest: {body}")
    
    try:
        # Initialize storage
        storage = PostgresAgentStorage(db_url=db_url, table_name=f'{agent_id.value}_sessions')
        
        # Get all sessions for this user
        sessions = storage.get_all_sessions(user_id=body.user_id)
        
        # Check if we need to filter by session_id
        if body.session_id:
            # Convert each session to dict first, then filter
            session_dicts = [session.to_dict() for session in sessions]
            session_dicts = [s for s in session_dicts if s.get("session_id") == body.session_id]
        else:
            # Convert all sessions to dicts
            session_dicts = [session.to_dict() for session in sessions]
            
        if not session_dicts:
            return []
            
        # Extract conversation messages from all sessions
        conversation_messages = []
        
        for session in session_dicts:
            # Access the messages array from the memory object
            if "memory" in session and "messages" in session["memory"]:
                messages = session["memory"]["messages"]
                
                # Filter out system messages, keep only user and assistant messages
                for msg in messages:
                    if msg.get("role") in ["user", "assistant"]:
                        # Create a simplified message object with just the essential fields
                        simplified_msg = {
                            "role": msg.get("role"),
                            "content": msg.get("content"),
                            "created_at": msg.get("created_at")
                        }
                        conversation_messages.append(simplified_msg)
        
        # Sort messages by timestamp if available
        conversation_messages.sort(key=lambda x: x.get("created_at", 0))
        
        # Apply limit if specified
        if body.limit and len(conversation_messages) > body.limit:
            conversation_messages = conversation_messages[-body.limit:]
            
        return conversation_messages
        
    except Exception as e:
        logger.error(f"Error retrieving chat history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve message history: {str(e)}"
        )


class SuggestedTopicsRequest(BaseModel):
    """Request model for retrieving suggested crypto topics"""
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    model: Model = Model.gpt_4o


@agents_router.post("/crypto/suggested-topics", status_code=status.HTTP_200_OK, response_model=CryptoQuestionsOutput)
async def get_suggested_crypto_topics(body: SuggestedTopicsRequest):
    """
    POST /agents/crypto/suggested-topics
    
    Generates a list of suggested crypto topics and questions for users to ask about.
    
    Args:
        body: Request parameters including user_id and session_id
        
    Returns:
        Structured output with market overview and list of suggested questions
    """
    logger.debug(f"SuggestedTopicsRequest: {body}")
    
    try:
        # Call the helper function that properly handles the workflow execution
        result = await suggest_crypto_questions_with_cache(
            model_id=body.model.value,
            user_id=body.user_id,
            session_id=body.session_id,
            use_cache=True,
            cache_ttl_hours=3
        )
        return result
        
    except Exception as e:
        logger.error(f"Error generating suggested topics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate suggested topics: {str(e)}"
        )
    