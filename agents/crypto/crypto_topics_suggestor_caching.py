import time
import sqlalchemy as sa
from sqlalchemy import engine
from datetime import datetime
from typing import Iterator, Optional
from pydantic import BaseModel, Field

from agno.utils.log import logger
from agno.workflow import RunResponse

from agents.crypto.crypto_topics_suggestor import CryptoTopicsSuggestorWorkflow, CryptoTopicsList, CryptoQuestionsOutput

from textwrap import dedent
from typing import Optional, List, Iterator, Dict, Any
import json
import hashlib

from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.storage.agent.postgres import PostgresAgentStorage
from agno.workflow import Workflow, RunResponse
from agno.utils.log import logger

from sqlalchemy.orm import Session, declarative_base, sessionmaker

from db.session import db_url

# Create our own engine using the db_url
engine = sa.create_engine(db_url)

# Create a base class for SQLAlchemy models
Base = declarative_base()

# Create a sessionmaker
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Define a model for cache storage
class CryptoCache(Base):
    __tablename__ = "crypto_topics_cache"
    
    cache_key = sa.Column(sa.String, primary_key=True)
    cache_data = sa.Column(sa.JSON)
    created_at = sa.Column(sa.DateTime, default=datetime.utcnow)
    updated_at = sa.Column(sa.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Create the cache table if it doesn't exist
Base.metadata.create_all(bind=engine)


class CachedCryptoTopicsSuggestorWorkflow(CryptoTopicsSuggestorWorkflow):
    """Enhanced workflow with persistent caching mechanisms to reduce API calls and improve performance."""
    
    def __init__(
        self,
        model_id: str = "gpt-4o",
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        debug_mode: bool = True,
        use_cache: bool = True,
        cache_ttl_hours: int = 3  # Cache time-to-live in hours
    ):
        super().__init__(
            model_id=model_id,
            user_id=user_id,
            session_id=session_id,
            debug_mode=debug_mode,
        )
        self.use_cache = use_cache
        self.cache_ttl_hours = cache_ttl_hours
        
        # Use the user_id and session_id in the cache keys to maintain separate caches per user/session
        self.user_context = f"{user_id or 'anonymous'}_{session_id or 'default'}"
        
    def get_cache_key(self, prefix: str = "") -> str:
        """Generate a cache key based on model and user context."""
        model_name = getattr(self.topics_seeker.model, 'id', 'default-model')
        return f"{prefix}_{model_name}_{self.user_context}"
    
    def is_cache_valid(self, cache_key: str) -> bool:
        """Check if the cached data is still valid based on TTL by checking database."""
        if not self.use_cache:
            return False
        
        # Create a new session for this operation
        db = SessionLocal()
        try:
            # Query the database for this cache key
            result = db.query(CryptoCache).filter(CryptoCache.cache_key == cache_key).first()
            
            if not result:
                return False
                
            # Check if cache has expired based on TTL
            cache_age_hours = (datetime.utcnow() - result.updated_at).total_seconds() / 3600
            return cache_age_hours < self.cache_ttl_hours
        finally:
            db.close()
    
    def get_cached_topics(self) -> Optional[CryptoTopicsList]:
        """Get cached topics if available and valid from database."""
        logger.info("Checking for cached crypto topics")
        cache_key = self.get_cache_key("topics")
        
        if self.is_cache_valid(cache_key):
            # Create a new session for this operation
            db = SessionLocal()
            try:
                # Query the database for this cache key
                result = db.query(CryptoCache).filter(CryptoCache.cache_key == cache_key).first()
                    
                if result and result.cache_data:
                    logger.info(f"Using cached topics from {self.cache_ttl_hours} hour window")
                    return CryptoTopicsList.model_validate(result.cache_data)
            finally:
                db.close()
        
        logger.info("No valid cached topics found")
        return None
    
    def cache_topics(self, topics: CryptoTopicsList) -> None:
        """Save topics to database cache with current timestamp."""
        if not self.use_cache:
            return
            
        logger.info("Caching crypto topics to database")
        cache_key = self.get_cache_key("topics")
        topics_data = topics.model_dump()
        
        # Create a new session for this operation
        db = SessionLocal()
        try:
            # Check if entry already exists
            existing = db.query(CryptoCache).filter(CryptoCache.cache_key == cache_key).first()
            
            if existing:
                # Update existing entry
                existing.cache_data = topics_data
                existing.updated_at = datetime.utcnow()
            else:
                # Insert new entry
                new_cache = CryptoCache(
                    cache_key=cache_key,
                    cache_data=topics_data,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                db.add(new_cache)
            
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Error caching topics: {e}")
        finally:
            db.close()
    
    def get_cached_questions(self, topics_hash: str) -> Optional[CryptoQuestionsOutput]:
        """Get cached questions from database if available and valid."""
        logger.info("Checking for cached crypto questions")
        cache_key = self.get_cache_key(f"questions_{topics_hash}")
        
        if self.is_cache_valid(cache_key):
            # Create a new session for this operation
            db = SessionLocal()
            try:
                # Query the database for this cache key
                result = db.query(CryptoCache).filter(CryptoCache.cache_key == cache_key).first()
                
                if result and result.cache_data:
                    logger.info(f"Using cached questions from {self.cache_ttl_hours} hour window")
                    return CryptoQuestionsOutput.model_validate(result.cache_data)
            finally:
                db.close()
        
        logger.info("No valid cached questions found")
        return None
    
    def cache_questions(self, questions: CryptoQuestionsOutput, topics_hash: str) -> None:
        """Save questions to database cache with current timestamp."""
        if not self.use_cache:
            return
            
        logger.info("Caching crypto questions to database")
        cache_key = self.get_cache_key(f"questions_{topics_hash}")
        questions_data = questions.model_dump()
        
        # Create a new session for this operation
        db = SessionLocal()
        try:
            # Check if entry already exists
            existing = db.query(CryptoCache).filter(CryptoCache.cache_key == cache_key).first()
            
            if existing:
                # Update existing entry
                existing.cache_data = questions_data
                existing.updated_at = datetime.utcnow()
            else:
                # Insert new entry
                new_cache = CryptoCache(
                    cache_key=cache_key,
                    cache_data=questions_data,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                db.add(new_cache)
            
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Error caching questions: {e}")
        finally:
            db.close()
    
    def generate_topics_hash(self, topics: CryptoTopicsList) -> str:
        """Generate a simple hash from topics list for cache key."""
        # Simple string hash for topics to use as part of cache key
        titles = [topic.title for topic in topics.topics]
        titles_str = "_".join(titles)
        return hashlib.md5(titles_str.encode()).hexdigest()[:8]
    
    def get_news_topics(self) -> CryptoTopicsList:
        """Get crypto news topics with database caching."""
        # Check cache first
        cached_topics = self.get_cached_topics()
        if cached_topics:
            return cached_topics
            
        # If no cached data, call parent implementation
        topics = super().get_news_topics()
        
        # Cache the result
        self.cache_topics(topics)
        
        return topics
    
    def get_questions_proposal(self, crypto_topics: CryptoTopicsList) -> CryptoQuestionsOutput:
        """Get question proposals with database caching."""
        # Generate a hash for these specific topics
        topics_hash = self.generate_topics_hash(crypto_topics)
        
        # Check cache first
        cached_questions = self.get_cached_questions(topics_hash)
        if cached_questions:
            return cached_questions
            
        # If no cached data, call parent implementation
        questions = super().get_questions_proposal(crypto_topics)
        
        # Cache the result
        self.cache_questions(questions, topics_hash)
        
        return questions
    
    def run(self) -> Iterator[RunResponse]:
        """Run the workflow with database caching."""
        logger.info(f"Starting Cached Crypto Topics Suggestor Workflow (cache {'enabled' if self.use_cache else 'disabled'})")
        
        # Delegate to parent implementation
        yield from super().run()


def get_cached_crypto_topics_suggestor(
    model_id: str = "gpt-4o",
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    debug_mode: bool = True,
    use_cache: bool = True,
    cache_ttl_hours: int = 3
) -> CachedCryptoTopicsSuggestorWorkflow:
    """Get a cached crypto topics suggestor workflow instance."""
    return CachedCryptoTopicsSuggestorWorkflow(
        model_id=model_id,
        user_id=user_id,
        session_id=session_id,
        debug_mode=debug_mode,
        use_cache=use_cache,
        cache_ttl_hours=cache_ttl_hours
    )


async def suggest_crypto_questions_with_cache(
    model_id: str = "gpt-4o",
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    debug_mode: bool = True,
    use_cache: bool = True,
    cache_ttl_hours: int = 3
) -> CryptoQuestionsOutput:
    """Generate suggested crypto questions using the cached workflow."""
    workflow = get_cached_crypto_topics_suggestor(
        model_id=model_id,
        user_id=user_id,
        session_id=session_id,
        debug_mode=debug_mode,
        use_cache=use_cache,
        cache_ttl_hours=cache_ttl_hours
    )
    
    last_response = None
    for response in workflow.run():
        if isinstance(response.content, CryptoQuestionsOutput):
            return response.content
        last_response = response
    
    # If we don't get a proper response, return default questions
    if last_response and isinstance(last_response.content, CryptoQuestionsOutput):
        return last_response.content
    
    return workflow.create_default_questions()