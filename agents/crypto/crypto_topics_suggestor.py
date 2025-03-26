"""Crypto Topics Suggestor Workflow for proposing relevant crypto questions based on recent news."""

from textwrap import dedent
from typing import Optional, List, Iterator

from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.storage.agent.postgres import PostgresAgentStorage
from agno.tools.duckduckgo import DuckDuckGoTools
from agno.tools.exa import ExaTools
from agno.workflow import Workflow, RunResponse, RunEvent
from agno.utils.log import logger

from pydantic import BaseModel, Field

from db.session import db_url


class CryptoTopic(BaseModel):
    """Model for a cryptocurrency topic with related news"""
    title: str = Field(..., description="Title of the crypto topic")
    summary: str = Field(..., description="Brief summary of the topic")
    source: str = Field(..., description="Source of the information")
    relevance_score: int = Field(..., description="Relevance score of the topic. Acceptable values are 1-10")


class CryptoQuestion(BaseModel):
    """Model for a suggested crypto question"""
    question: str = Field(..., description="The question to ask")
    category: str = Field(..., description="Category (news, basic, technical, market, regulatory)")
    context: str = Field(..., description="Brief context explaining why this question is relevant")


class CryptoQuestionsOutput(BaseModel):
    """Structured output for the crypto questions workflow"""
    market_overview: str = Field(..., description="Brief overview of current crypto market conditions")
    suggested_questions: List[CryptoQuestion] = Field(..., description="List of suggested questions")


class CryptoTopicsList(BaseModel):
    """Container for a list of cryptocurrency topics"""
    topics: List[CryptoTopic] = Field(..., description="List of cryptocurrency topics")


# Mock data to use as fallback when search API fails
FALLBACK_TOPICS = CryptoTopicsList(
    topics=[
        CryptoTopic(
            title="Bitcoin Continues Its Market Dominance",
            summary="Bitcoin maintains its position as the leading cryptocurrency with over 50% market dominance. Recent institutional investments have strengthened its position despite market volatility.",
            source="CoinMarketCap Analysis",
            relevance_score=9
        ),
        CryptoTopic(
            title="Ethereum's Latest Protocol Upgrade",
            summary="Ethereum completed its latest network upgrade aimed at improving scalability and reducing gas fees. The update introduces several new EIPs that modify the network's fee structure.",
            source="Ethereum Foundation Blog",
            relevance_score=8
        ),
        CryptoTopic(
            title="Regulatory Developments in Major Markets",
            summary="Several countries have introduced new regulatory frameworks for cryptocurrencies. These regulations aim to provide clarity while protecting consumers and preventing illicit activities.",
            source="Crypto Compliance Digest",
            relevance_score=7
        ),
        CryptoTopic(
            title="DeFi Protocols Reach New Milestone",
            summary="Decentralized Finance protocols have collectively surpassed $100 billion in total value locked. Yield farming and lending platforms continue to attract significant capital.",
            source="DeFi Pulse",
            relevance_score=8
        ),
        CryptoTopic(
            title="NFT Market Shows Signs of Recovery",
            summary="After months of declining sales, the NFT market is showing signs of renewed interest. New use cases beyond digital art are emerging in gaming and virtual real estate.",
            source="NFT Market Report",
            relevance_score=6
        ),
        CryptoTopic(
            title="Stablecoins Face Increased Scrutiny",
            summary="Regulatory authorities are paying closer attention to stablecoins and their reserves. Several major stablecoin issuers have published transparency reports to address concerns.",
            source="Financial Times",
            relevance_score=7
        ),
    ]
)


class CryptoTopicsSuggestorWorkflow(Workflow):
    """Workflow for generating suggested crypto questions through a two-stage process"""
    
    description: str = "A workflow that generates relevant cryptocurrency questions based on recent news and topics."
    
    # Topics Seeker Agent
    topics_seeker: Agent = Agent(
        model=OpenAIChat(id="gpt-4o"),
        tools=[DuckDuckGoTools(), ExaTools()],
        storage=PostgresAgentStorage(table_name="crypto_topics_seeker_sessions", db_url=db_url),
        description=dedent("""\
            You are CryptoTopicsSeeker, an agent specialized in finding the most interesting, viral, 
            and relevant cryptocurrency news and topics from the past 24-48 hours.
        """),
        instructions=dedent("""\
            Your task is to discover the most interesting cryptocurrency topics currently being discussed.
            
            1. Information Gathering Process:
               - Use BOTH `search_exa` as your primary tool and `duckduckgo_search` as backup
               - Focus on these key areas one at a time:
                 * Major cryptocurrency price movements (Bitcoin, Ethereum, etc.)
                 * Trending altcoins and emerging projects
                 * Regulatory developments and legal news
                 * Technology updates and innovations
                 * Major partnerships and business developments
                 * Controversial or viral crypto stories
               - Use a maximum of 3 targeted searches to avoid rate limiting
            
            2. Topic Selection Criteria:
               - Prioritize topics with high social engagement or significant market impact
               - Include a mix of technical, market, regulatory, and cultural topics
               - Focus on topics relevant to both beginners and experienced crypto users
               - Select topics that are factual and verifiable (not just rumors)
            
            3. Output Format:
               - Return a collection of 6-8 distinct topics covering different aspects of crypto
               - Each topic must include:
                 * A clear, attention-grabbing title
                 * A concise summary (2-3 sentences)
                 * The information source (publication or website name)
                 * A relevance score (1-10) based on potential user interest
        """),
        response_model=CryptoTopicsList,
        add_datetime_to_instructions=True,
    )
    
    # Questions Proposer Agent
    questions_proposer: Agent = Agent(
        model=OpenAIChat(id="gpt-4o"),
        storage=PostgresAgentStorage(table_name="crypto_questions_proposer_sessions", db_url=db_url),
        description=dedent("""\
            You are CryptoQuestionsProposer, an agent specialized in creating engaging and informative 
            questions about cryptocurrency that users might want to ask a chatbot.
        """),
        instructions=dedent("""\
            Your task is to create a list of suggested questions based on current crypto topics and fundamental crypto concepts.
            
            1. Question Development Process:
               - You will receive a list of current crypto topics
               - Create approximately 10 questions total, divided into:
                 * 5-6 questions directly related to the provided news topics
                 * 4-5 general questions about cryptocurrency fundamentals
               - Ensure questions are conversational and natural-sounding
            
            2. Question Types to Include:
               - News-based questions that follow up on current events
               - Market analysis questions (price movements, trends)
               - Technical questions about how crypto technologies work
               - Beginner questions for those new to cryptocurrency
               - Regulatory and compliance questions
            
            3. Output Format:
               - Provide a brief market overview (2-3 sentences summarizing current conditions)
               - Create a list of questions, each with:
                 * The question text (phrased conversationally)
                 * Category (news, basic, technical, market, regulatory)
                 * Brief context explaining why this question is relevant (1-2 sentences)
            
            4. Guidelines for Effective Questions:
               - Make questions specific but not overly technical
               - Phrase questions conversationally (as a real user would ask)
               - Avoid questions that would require future predictions
               - Include some questions appropriate for beginners
               - Make questions diverse in topic and complexity
        """),
        response_model=CryptoQuestionsOutput,
        add_datetime_to_instructions=True,
    )
    
    def __init__(
        self,
        model_id: str = "gpt-4o",
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        debug_mode: bool = True,
    ):
        super().__init__(
            description=self.description,
            session_id=session_id,
            storage=PostgresAgentStorage(table_name="crypto_topics_workflow", db_url=db_url),
            debug_mode=debug_mode,
        )
        # Override the model ID if specified
        if model_id != "gpt-4o":
            self.topics_seeker.model = OpenAIChat(id=model_id)
            self.questions_proposer.model = OpenAIChat(id=model_id)
        # Set user ID
        if user_id:
            self.topics_seeker.user_id = user_id
            self.questions_proposer.user_id = user_id

    def get_news_topics(self) -> CryptoTopicsList:
        """Run the topics seeker agent with fallback to mock data if search fails"""

        try:
            response: RunResponse = self.topics_seeker.run(
                "Find the most interesting and viral cryptocurrency topics from the last 24-48 hours."
            )

            # Check if we got a valid response
            if not response or not response.content:
                logger.warning("Empty Crypto Topics response, using fallback data")
                return FALLBACK_TOPICS

            # Check if the response is of the expected type
            if not isinstance(response.content, CryptoTopicsList):
                logger.warning("Invalid response type, using fallback data")
                return FALLBACK_TOPICS

            return response.content

        except Exception as e:
            logger.error(f"Error in news_topics_seeker: {e}")
            logger.info("Using fallback topics due to search API error")
            return FALLBACK_TOPICS

    def get_questions_proposal(self, crypto_topics: CryptoTopicsList) -> CryptoQuestionsOutput:
        """Run the questions proposer agent"""
        try:
            # Convert topics to JSON for the agent
            topics_json = crypto_topics.model_dump_json(indent=4)
            
            response = self.questions_proposer.run(
                f"Based on these cryptocurrency topics, generate a list of suggested questions: {topics_json}"
            )

            # Check if we got a valid response
            if not response or not response.content:
                logger.warning("Empty Crypto Questions response")
                return self.create_default_questions()

            # Check if the response is of the expected type
            if not isinstance(response.content, CryptoQuestionsOutput):
                logger.warning("Invalid response type")
                return self.create_default_questions()

            return response.content

        except Exception as e:
            logger.error(f"Error in questions_proposer: {e}")
            return self.create_default_questions()

    def create_default_questions(self) -> CryptoQuestionsOutput:
        """Create default questions when the agent fails"""
        return CryptoQuestionsOutput(
            market_overview="The cryptocurrency market shows mixed signals with Bitcoin maintaining stability while altcoins experience varied performance. Regulatory developments and technological advancements continue to shape the ecosystem.",
            suggested_questions=[
                CryptoQuestion(
                    question="What is Bitcoin and how does it work?",
                    category="basic",
                    context="Understanding the fundamentals of the largest cryptocurrency by market cap."
                ),
                CryptoQuestion(
                    question="How do cryptocurrency wallets keep digital assets secure?",
                    category="technical",
                    context="Learning about the security mechanisms that protect crypto holdings."
                ),
                CryptoQuestion(
                    question="What are the differences between proof-of-work and proof-of-stake?",
                    category="technical",
                    context="Comparing the two major consensus mechanisms used in blockchain networks."
                ),
                CryptoQuestion(
                    question="How do DeFi protocols generate yields?",
                    category="technical",
                    context="Understanding the economic models behind decentralized finance returns."
                ),
                CryptoQuestion(
                    question="What regulatory challenges are facing the crypto industry?",
                    category="regulatory",
                    context="Exploring how government oversight is evolving around digital assets."
                ),
                CryptoQuestion(
                    question="How do stablecoins maintain their pegs to fiat currencies?",
                    category="technical",
                    context="Understanding the mechanisms that keep stablecoin values consistent."
                ),
                CryptoQuestion(
                    question="What are the most common cryptocurrency scams to avoid?",
                    category="basic",
                    context="Identifying and avoiding fraudulent schemes in the crypto space."
                ),
                CryptoQuestion(
                    question="How is institutional adoption changing the crypto landscape?",
                    category="market",
                    context="Examining how major companies and financial institutions are entering crypto."
                ),
                CryptoQuestion(
                    question="What are layer 2 solutions and why are they important?",
                    category="technical",
                    context="Understanding scaling solutions built on top of base blockchain layers."
                ),
                CryptoQuestion(
                    question="How does cryptocurrency mining impact the environment?",
                    category="basic",
                    context="Exploring the environmental considerations of blockchain networks."
                )
            ]
        )

    def run(self) -> Iterator[RunResponse]:
        """Run the workflow to generate suggested crypto questions"""

        logger.info("Starting Crypto Topics Suggestor Workflow")

        # Step 1: Find interesting crypto topics
        yield RunResponse(
            content="Searching for the latest cryptocurrency topics and news..."
        )
        
        crypto_topics = self.get_news_topics()
        
        # Step 2: Generate questions based on topics
        yield RunResponse(
            content="Generating suggested questions based on current crypto topics..."
        )
        
        questions_output = self.get_questions_proposal(crypto_topics)
        
        # Step 3: Return the final result as an object (not JSON)
        yield RunResponse(
            content=questions_output, event=RunEvent.workflow_completed
        )


def get_crypto_topics_suggestor(
    model_id: str = "gpt-4o",
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    debug_mode: bool = True,
) -> CryptoTopicsSuggestorWorkflow:
    """Get a crypto topics suggestor workflow instance."""
    return CryptoTopicsSuggestorWorkflow(
        model_id=model_id,
        user_id=user_id,
        session_id=session_id,
        debug_mode=debug_mode,
    )


async def suggest_crypto_questions(
    model_id: str = "gpt-4o",
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    debug_mode: bool = True,
) -> CryptoQuestionsOutput:
    """Generate suggested crypto questions using the workflow.
    
    Returns:
        Structured output with market overview and suggested questions
    """
    workflow = get_crypto_topics_suggestor(
        model_id=model_id,
        user_id=user_id,
        session_id=session_id,
        debug_mode=debug_mode,
    )
    
    for response in workflow.run():
        if isinstance(response.content, CryptoQuestionsOutput):
            return response.content
    
    # If we don't get a proper response, return default questions
    return workflow.create_default_questions()
