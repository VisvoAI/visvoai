"""
Durable memory with AsyncSqliteSaver.

Install the SQLite extra, which includes the optional dependencies needed
for durable checkpointing:

    pip install "visvoai-core[sqlite]"

Run:

    python examples/09_sqlite_durable_memory.py                 # runs with NO api key (scripted model)

Run the script twice using the same database file and thread_id.

First run:
    > remember that my favourite colour is teal

Second run:
    > what's my favourite colour?

The second run restores the previous conversation from SQLite,
demonstrating durable memory across process restarts.
"""

import asyncio

import aiosqlite
from langchain_core.language_models.fake_chat_models import (
    FakeMessagesListChatModel,
)
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from visvoai.core import ask
from visvoai.core.runtime import AgentRuntime

ROLE_NAMES = {
    "SystemMessage": "System",
    "HumanMessage": "User",
    "AIMessage": "Assistant",
}


class ScriptedModel(FakeMessagesListChatModel):
    """A tiny deterministic model for demonstrating durable memory.

    This model doesn't use an LLM. Instead, it inspects the conversation
    history passed to it by LangGraph. If previous messages were restored
    from the checkpoint, it can answer questions about them.
    """

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages, *args, **kwargs):
        # Ignore the system prompt and the current user message.
        restored_history = messages[1:-1]

        if restored_history:
            print("\nConversation restored from SQLite checkpoint:")
            print("-" * 50)

            for message in messages:
                role = ROLE_NAMES.get(type(message).__name__, type(message).__name__)
                print(f"{role}: {message.content}")

            print("-" * 50)

        # Find the latest user message.
        latest_human = next(
            (
                m.content.lower()
                for m in reversed(messages)
                if isinstance(m, HumanMessage)
            ),
            "",
        )

        # First run:
        # User: "remember that my favourite colour is teal"
        if "remember" in latest_human and "teal" in latest_human:
            return AIMessage(
                content="Okay! I'll remember that your favourite colour is teal."
            )

        # Second run:
        # User: "what's my favourite colour?"
        if "favourite colour" in latest_human or "favorite color" in latest_human:
            remembered = any(
                isinstance(m, HumanMessage)
                and "remember" in m.content.lower()
                and "teal" in m.content.lower()
                for m in messages[:-1]
            )

            if remembered:
                return AIMessage(content="Your favourite colour is teal.")

            return AIMessage(content="I don't know your favourite colour yet.")

        return AIMessage(content="I'm only scripted to demonstrate durable memory.")


async def main():
    # Store checkpoints in a local SQLite database so they survive process
    # restarts.
    conn = await aiosqlite.connect("agent_state.db")

    try:
        checkpointer = AsyncSqliteSaver(conn)

        graph = AgentRuntime().build_graph(
            model=ScriptedModel(responses=[]),
            core_tools=[],
            system_prompt="You are a helpful assistant.",
            checkpointer=checkpointer,
        )

        print("Durable Memory Demo")
        print("=" * 50)
        print("Run this script twice using the same database file.")
        print()
        print("First run:")
        print("  > remember that my favourite colour is teal")
        print()
        print("Second run:")
        print("  > what's my favourite colour?")
        print()
        print("Keep the same thread_id ('demo-thread') for both runs.")
        print("=" * 50)

        question = input("\n> ")

        # Reuse the same thread_id on every run.
        # LangGraph restores the conversation from the SQLite checkpoint.
        response = await ask(
            graph,
            question,
            thread_id="demo-thread",
        )

        print(f"\nAssistant: {response}")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())