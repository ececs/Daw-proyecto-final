"""LangGraph state schema for the AI agent.

`AgentState` is the dictionary shape the LangGraph runtime threads
through every node of the agent graph. The `Annotated[..., add_messages]`
hint lets LangGraph append new messages to the list automatically
instead of overwriting it, which is what enables stateful conversations.
"""

from typing import Annotated, Sequence, TypedDict
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """State carried across nodes of the ReAct agent graph.

    Attributes:
        messages: Conversation history; LangGraph appends to it via
            `add_messages`.
        remaining_steps: Required by `create_react_agent` to bound the
            ReAct loop and prevent runaway tool-call cycles.
    """
    messages: Annotated[Sequence[BaseMessage], add_messages]
    remaining_steps: int


class AgentConfig(BaseModel):
    """Per-invocation configuration bound to a chat session.

    Used to scope checkpoints and tool authorisation to the right
    conversation and user.
    """
    thread_id: str = Field(..., description="Unique session identifier")
    user_id: str = Field(..., description="ID of the user interacting with the agent")
