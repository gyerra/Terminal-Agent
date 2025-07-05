import os
from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.prebuilt import ToolNode
from typing import TypedDict, Sequence, Annotated
from langchain_core.tools import tool
from terminal_controller import Process
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

load_dotenv()

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]

pw = Process()

@tool
def send_command(cmd: str) -> str:
    """Execute a command in the PowerShell session and return the output"""
    try:
        output = pw.send_command(cmd)
       
        if output:
            lines = output.splitlines()
            cleaned_lines = [line for line in lines 
                           if not line.strip().startswith('<<<<START_MARKER') 
                           and not line.strip().startswith('<<<<END_MARKER')]
            cleaned_output = '\n'.join(cleaned_lines).strip()
            return cleaned_output if cleaned_output else "No output returned from command."
        return "No output returned from command."
    except Exception as e:
        return f"Error executing command '{cmd}': {str(e)}"

def get_llm():
    """Initialize and return the appropriate LLM"""
    model_provider = os.getenv('MODEL_PROVIDER', 'gemini').lower()
    
    if model_provider == 'openai':
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=os.getenv('OPENAI_MODEL', 'gpt-4o'),
            api_key=os.getenv('OPENAI_API_KEY')
        ).bind_tools([send_command])
    else:
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=os.getenv('GEMINI_MODEL', 'gemini-2.5-flash'),
            google_api_key=os.getenv('GEMINI_API_KEY'),
            temperature=0.1,
            convert_system_message_to_human=True
        ).bind_tools([send_command])

llm = get_llm()

def agent_node(state: AgentState) -> AgentState:
    """Main agent node that processes user input"""
    system_prompt = SystemMessage(
        """You are a terminal agent running on Windows with PowerShell access. 
        Help users execute commands and tasks efficiently.
        
        Guidelines:
        - Use modern PowerShell commands
        - Retry with alternative commands if something fails
        - Don't repeat user input unless explicitly asked
        - For .gitignore files, analyze directory contents to make smart decisions
        - Be concise and helpful"""
    )
    
    try:
        response = llm.invoke([system_prompt] + state["messages"])
        return {"messages": [response]}
    except Exception as e:
        return {"messages": [AIMessage(content=f"Error: {str(e)}")]}

def should_continue(state: AgentState) -> str:
    """Determine if we should continue with tool calls"""
    last_message = state["messages"][-1]
    return "continue" if last_message.tool_calls else "end"

graph = StateGraph(AgentState)
graph.add_node("agent", agent_node)
graph.add_node("tools", ToolNode([send_command]))
graph.add_edge(START, "agent")
graph.add_edge("tools", "agent")
graph.add_conditional_edges("agent", should_continue, {"continue": "tools", "end": END})

agent = graph.compile()

def run_cli():
    """Run the CLI version of the agent"""
    print("🚀 Terminal Agent CLI")
    print("Type 'exit' to quit\n")
    
    conversation_history = []
    
    while True:
        user_input = input("Command: ")
        if user_input.lower() == "exit":
            break
            
        conversation_history.append(HumanMessage(content=user_input))
        inputs = {"messages": conversation_history}
        
        for chunk in agent.stream(inputs, {"recursion_limit": 35}, stream_mode="values"):
            message = chunk["messages"][-1]
            if hasattr(message, 'pretty_print'):
                message.pretty_print()
            else:
                print(message)
        
        final_result = agent.invoke(inputs, {"recursion_limit": 35})
        conversation_history = final_result["messages"]

if __name__ == "__main__":
    run_cli()