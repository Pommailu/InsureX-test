from typing import List, Optional, Sequence, Annotated
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from lead_models import CustomerLead

class AgentState(BaseModel):
    """
    LangGraph Workflow State for InsureX AI Sales Agent.
    Maintains full conversation history, session identification,
    classified intent, lead collection status, and RAG contexts.
    """
    # Message history with automatic append reducer
    messages: Annotated[Sequence[BaseMessage], add_messages] = Field(default_factory=list)
    
    # Session identifier for session separation & multi-user memory
    session_id: str = Field(default="default_session")
    
    # User intent classification
    # 'rag_inquiry' | 'product_interest' | 'lead_info_provided' | 'general_chat' | 'out_of_scope'
    customer_intent: str = Field(default="rag_inquiry")
    
    # Accumulated structured customer lead data
    lead_info: Optional[CustomerLead] = Field(default=None)
    
    # Flag whether lead has been successfully validated and saved to SQLite
    lead_saved: bool = Field(default=False)
    
    # Retrieved documents context from ChromaDB
    retrieved_context: str = Field(default="")
    
    # Whether RAG found relevant knowledge meeting distance threshold
    rag_found: bool = Field(default=True)
    
    # Error status or reason if information not found
    error_status: Optional[str] = Field(default=None)
    
    # Final generated response text
    final_response: str = Field(default="")
