from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from dotenv import load_dotenv
from langgraph.prebuilt import ToolNode
from typing import TypedDict, Sequence, Annotated
from langchain_core.tools import tool
from terminal_controller import Process
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from langchain_google_genai import ChatGoogleGenerativeAI
from config import get_config
import json
import os
import logging
import sys
from pathlib import Path

# Load environment variables
load_dotenv()

def check_gemini_key():
    """Check if Gemini API key is configured"""
    env_file = Path(".env")
    if not env_file.exists():
        print("⚠️  .env file not found!")
        print("\n📝 Please create a .env file with your Gemini API key:")
        print("GEMINI_API_KEY=your_gemini_api_key_here")
        print("\n🔑 Get your free Gemini API key from:")
        print("https://makersuite.google.com/app/apikey")
        print("\n💡 You can still run the app to see the UI (AI features will be limited)")
        return False
    
    # Check if API key is set
    with open(env_file, 'r') as f:
        content = f.read()
        if 'your_gemini_api_key_here' in content:
            print("⚠️  Please update your .env file with your actual Gemini API key!")
            print("🔑 Get your free API key from: https://makersuite.google.com/app/apikey")
            print("\n💡 You can still run the app to see the UI (AI features will be limited)")
            return False
    
    print("✅ Gemini API key configured")
    return True

# Configure logging
config = get_config()
logging.basicConfig(
    level=config.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(config)

# Configure CORS
if config.ENABLE_CORS:
    CORS(app, origins=config.ALLOWED_ORIGINS)

# Initialize the PowerShell process
try:
    pw = Process()
    logger.info("PowerShell process initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize PowerShell process: {e}")
    pw = None

class AgentState(TypedDict):
    messages : Annotated[Sequence[BaseMessage],add_messages]

@tool
def send_command(cmd: str) -> str:
    """Takes a command string, executes it in the PowerShell session, and returns the output"""
    if not pw:
        return "Error: PowerShell process is not available"
    
    try:
        output = pw.send_command(cmd)
        # Clean up marker lines and extra whitespace
        lines = output.splitlines()
        cleaned_lines = [line for line in lines if not line.strip().startswith('<<<<START_MARKER') and not line.strip().startswith('<<<<END_MARKER')]
        cleaned_output = '\n'.join(cleaned_lines).strip()
        return cleaned_output if cleaned_output else "No output returned from command."
    except Exception as e:
        error_msg = f"Error executing command '{cmd}': {str(e)}"
        logger.error(error_msg)
        return error_msg

tools = [send_command]

# Initialize the LLM based on provider
llm = None
model_provider = os.getenv('MODEL_PROVIDER', 'gemini').lower()
try:
    if model_provider == 'openai':
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            model_name=config.OPENAI_MODEL,
            api_key=config.OPENAI_API_KEY
        ).bind_tools(tools)
        logger.info(f"OpenAI LLM initialized with model: {config.OPENAI_MODEL}")
    else:
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(
            model=config.GEMINI_MODEL,
            google_api_key=config.GEMINI_API_KEY,
            temperature=0.1,
            convert_system_message_to_human=True
        ).bind_tools(tools)
        logger.info(f"Gemini LLM initialized with model: {config.GEMINI_MODEL}")
except Exception as e:
    logger.error(f"Failed to initialize LLM: {e}")
    llm = None

def agent_node(state: AgentState) -> AgentState:
    """Agent Node"""
    if not llm:
        return {
            "messages": state["messages"] + [AIMessage(content="Error: AI model is not available")]
        }
    
    system_prompt = SystemMessage(
        """
        You are a terminal agent running on a Windows operating system, equipped with PowerShell session creation and command execution tools. Help the user with the best of your ability.
        - If you are not able to perform anything, automatically retry with an other command until you do it.
        - Strictly use Latest Powershell commands.
        - You are a highly intelligent and fast terminal assistant agent.
        - Often times you are able to perform the action correctly but you are thinking you didn't perform it and you are trying to re-do it. Please be mindful of this and act properly.
        - When asked to create a gitignore file, read the contents of the directory and make a suitable desicion to keep what all files and directories in the git repository. See the file extensions to find out which language is being used.
        - Do not repeat or restate the user's input in your response unless explicitly asked.
        """
    )
    try:
        response = llm.invoke([system_prompt] + state["messages"])
        return {"messages": [response] + state["messages"]}
    except Exception as e:
        logger.error(f"Error in agent_node: {e}")
        return {
            "messages": state["messages"] + [AIMessage(content=f"Error processing request: {str(e)}")]
        }

def should_continue(state: AgentState) -> str:
    """Simple decider that only checks for tool calls"""
    messages_dict = state["messages"]
    last_message = messages_dict[-1]
    if not last_message.tool_calls:
        return "end"
    else: 
        return "continue"

# Build the graph
try:
    graph = StateGraph(AgentState)
    tool_node = ToolNode(tools=tools)
    graph.add_node("tool_node", tool_node)
    graph.add_node("agent_node", agent_node)
    graph.add_edge(START, "agent_node")
    graph.add_edge("tool_node", "agent_node")
    graph.add_conditional_edges(
        "agent_node",
        should_continue,
        {
            "continue": "tool_node",
            "end": END,
            "": "tool_node"
        }
    )
    agent = graph.compile()
    logger.info("LangGraph agent compiled successfully")
except Exception as e:
    logger.error(f"Failed to compile LangGraph agent: {e}")
    agent = None

# Global conversation history
conversation_history = []

@app.route('/')
def index():
    """Serve the main HTML page"""
    return render_template('index.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    """Handle chat requests"""
    if not agent:
        return jsonify({'error': 'Agent is not available', 'success': False}), 503
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        user_message = data.get('message', '')
        
        if not user_message:
            return jsonify({'error': 'No message provided'}), 400
        
        if len(user_message) > config.MAX_MESSAGE_LENGTH:
            return jsonify({'error': 'Message too long'}), 400
        
        # Add user message to conversation history
        conversation_history.append(HumanMessage(content=user_message))
        inputs = {"messages": conversation_history}
        
        # Process the message through the agent
        final_result = agent.invoke(inputs, {"recursion_limit": config.RECURSION_LIMIT})
        conversation_history.clear()
        conversation_history.extend(final_result["messages"])
        
        # Extract the AI response
        ai_response = None
        for message in final_result["messages"]:
            if isinstance(message, AIMessage):
                ai_response = message.content
                break
        
        # Debug logging
        logger.info(f"User message: {user_message}")
        logger.info(f"Raw AI response: {ai_response}")
        
        if not ai_response:
            ai_response = "No response generated"
        
        # Remove exact user input echo from AI response
        if ai_response and ai_response.strip().lower() == user_message.strip().lower():
            ai_response = "(No additional response generated by AI.)"
        
        logger.info(f"Processed chat request: {user_message[:50]}...")
        
        return jsonify({
            'response': ai_response,
            'success': True
        })
        
    except Exception as e:
        logger.error(f"Error processing chat request: {e}")
        return jsonify({
            'error': f'Error processing request: {str(e)}',
            'success': False
        }), 500

@app.route('/api/stream', methods=['POST'])
def stream_chat():
    """Handle streaming chat requests"""
    if not agent:
        return jsonify({'error': 'Agent is not available', 'success': False}), 503
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        user_message = data.get('message', '')
        
        if not user_message:
            return jsonify({'error': 'No message provided'}), 400
        
        if len(user_message) > config.MAX_MESSAGE_LENGTH:
            return jsonify({'error': 'Message too long'}), 400
        
        # Add user message to conversation history
        conversation_history.append(HumanMessage(content=user_message))
        inputs = {"messages": conversation_history}
        
        def generate():
            try:
                for chunk in agent.stream(inputs, {"recursion_limit": config.RECURSION_LIMIT}, stream_mode="values"):
                    message = chunk["messages"][-1]
                    if isinstance(message, tuple):
                        logger.info(f"Streamed tuple message: {message}")
                        yield f"data: {json.dumps({'type': 'message', 'content': str(message)})}\n\n"
                    else:
                        content = message.content if hasattr(message, 'content') else str(message)
                        logger.info(f"Streamed AI message: {content}")
                        # Remove exact user input echo from streamed AI message
                        if content.strip().lower() == user_message.strip().lower():
                            continue
                        yield f"data: {json.dumps({'type': 'message', 'content': content})}\n\n"
                
                # Update conversation history with final result
                final_result = agent.invoke(inputs, {"recursion_limit": config.RECURSION_LIMIT})
                conversation_history.clear()
                conversation_history.extend(final_result["messages"])
                
                yield f"data: {json.dumps({'type': 'end'})}\n\n"
                
            except Exception as e:
                logger.error(f"Error in stream generation: {e}")
                yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
        
        logger.info(f"Started streaming response for: {user_message[:50]}...")
        
        return app.response_class(
            generate(),
            mimetype='text/plain'
        )
        
    except Exception as e:
        logger.error(f"Error processing stream request: {e}")
        return jsonify({
            'error': f'Error processing request: {str(e)}',
            'success': False
        }), 500

@app.route('/api/clear', methods=['POST'])
def clear_history():
    """Clear conversation history"""
    global conversation_history
    conversation_history.clear()
    logger.info("Conversation history cleared")
    return jsonify({'success': True, 'message': 'Conversation history cleared'})

@app.route('/api/status', methods=['GET'])
def status():
    """Check API status"""
    status_info = {
        'status': 'running',
        'message': 'Terminal Agent API is running (Gemini)',
        'components': {
            'powershell': pw is not None,
            'llm': llm is not None,
            'agent': agent is not None
        }
    }
    return jsonify(status_info)

@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'})

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({'error': 'Internal server error'}), 500

def run_cli():
    """Run the CLI version"""
    print("🚀 Terminal Agent CLI (Gemini)")
    print("=" * 40)
    
    # Check API key
    has_api_key = check_gemini_key()
    if not has_api_key:
        print("\n⚠️  Running without API key - AI features will be limited")
    
    print("\n✅ Starting CLI...")
    print("💡 Type 'exit' to quit")
    print("=" * 40)
    
    conversation_history = []
    user_input = input("Command: ")
    while user_input != "exit":
        conversation_history.append(HumanMessage(content=user_input))
        inputs = {"messages": conversation_history}
        
        for chunk in agent.stream(inputs, {"recursion_limit": 35}, stream_mode="values"):
            message = chunk["messages"][-1]
            if isinstance(message, tuple):
                print(message)
            else:
                message.pretty_print()
        
        final_result = agent.invoke(inputs)
        conversation_history = final_result["messages"]
        
        user_input = input("Command: ")

if __name__ == '__main__':
    # Check if CLI mode is requested
    if len(sys.argv) > 1 and sys.argv[1] == '--cli':
        run_cli()
    else:
        # Web mode
        print("🚀 Terminal Agent Web Application (Gemini)")
        print("=" * 50)
        
        # Check API key but don't exit if missing
        has_api_key = check_gemini_key()
        
        if not has_api_key:
            print("\n⚠️  Running without API key - UI will work but AI features will be limited")
        
        print("\n✅ Starting web server...")
        print("🌐 Web server will be available at: http://localhost:5000")
        print("📱 Open your browser to access the Terminal Agent")
        print("🛑 Press Ctrl+C to stop the server")
        print("=" * 50)
        
        try:
            app.run(
                host=config.HOST,
                port=config.PORT,
                debug=config.DEBUG
            )
        except KeyboardInterrupt:
            print("\n\n👋 Server stopped by user")
        except Exception as e:
            print(f"\n❌ Error starting server: {e}")
            sys.exit(1) 