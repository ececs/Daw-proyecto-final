"""AI Agent execution state and configuration schema definitions.

Defines the schema for the AI agent's state using Pydantic-compatible
TypedDicts. By using Annotated and add_messages, we enable LangGraph to
automatically manage conversation history.
"""

from typing import Annotated, Sequence, TypedDict
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """Represents the active execution state of the conversational agent.

    Utilizes annotated message sequences allowing LangGraph to automatically accumulate,
    merge, and window conversational interaction histories.
    """
    messages: Annotated[Sequence[BaseMessage], add_messages]
    # Required by create_react_agent to prevent infinite loops
    remaining_steps: int


class AgentConfig(BaseModel):
    """Configures session metadata scoped to a single agent execution cycle.

    Provides unique thread and authenticated requester bindings to enforce context
    isolation and secure resource ownership in multi-tenant operations.
    """
    thread_id: str = Field(..., description="Unique session identifier")
    user_id: str = Field(..., description="ID of the user interacting with the agent")
