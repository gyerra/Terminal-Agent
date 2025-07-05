import os
import sys
import json
import logging
from pathlib import Path
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from langchain_core.messages import HumanMessage, AIMessage
from agent import agent

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-key-change-in-production')

CORS(app, origins=os.getenv('ALLOWED_ORIGINS', '*').split(','))

MAX_MESSAGE_LENGTH = int(os.getenv('MAX_MESSAGE_LENGTH', 1000))
RECURSION_LIMIT = int(os.getenv('RECURSION_LIMIT', 35))

conversation_history = []

def check_api_key():
    """Check if API key is configured"""
    env_file = Path(".env")
    if not env_file.exists():
        print("⚠️  .env file not found!")
        print("📝 Create a .env file with your API key:")
        print("GEMINI_API_KEY=your_api_key_here")
        print("🔑 Get your free Gemini API key: https://makersuite.google.com/app/apikey")
        return False
    
    with open(env_file, 'r') as f:
        content = f.read()
        if 'your_gemini_api_key_here' in content or 'your_openai_api_key_here' in content:
            print("⚠️  Please update your .env file with your actual API key!")
            return False
    
    print("✅ API key configured")
    return True

@app.route('/')
def index():
    """Serve the main HTML page"""
    return render_template('index.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    """Handle chat requests"""
    try:
        data = request.get_json()
        if not data or not data.get('message'):
            return jsonify({'error': 'No message provided'}), 400
        
        user_message = data['message']
        
        if len(user_message) > MAX_MESSAGE_LENGTH:
            return jsonify({'error': 'Message too long'}), 400
        
        conversation_history.append(HumanMessage(content=user_message))
        inputs = {"messages": conversation_history}
        
        result = agent.invoke(inputs, {"recursion_limit": RECURSION_LIMIT})
        conversation_history.clear()
        conversation_history.extend(result["messages"])
        
        ai_response = None
        for message in result["messages"]:
            if isinstance(message, AIMessage):
                ai_response = message.content
                break
        
        if not ai_response:
            ai_response = "No response generated"
        
        logger.info(f"Processed: {user_message[:50]}...")
        
        return jsonify({
            'response': ai_response,
            'success': True
        })
        
    except Exception as e:
        logger.error(f"Error processing request: {e}")
        return jsonify({
            'error': str(e),
            'success': False
        }), 500

@app.route('/api/stream', methods=['POST'])
def stream_chat():
    """Handle streaming chat requests"""
    try:
        data = request.get_json()
        if not data or not data.get('message'):
            return jsonify({'error': 'No message provided'}), 400
        
        user_message = data['message']
        
        if len(user_message) > MAX_MESSAGE_LENGTH:
            return jsonify({'error': 'Message too long'}), 400
        
        conversation_history.append(HumanMessage(content=user_message))
        inputs = {"messages": conversation_history}
        
        def generate():
            try:
                for chunk in agent.stream(inputs, {"recursion_limit": RECURSION_LIMIT}, stream_mode="values"):
                    message = chunk["messages"][-1]
                    content = message.content if hasattr(message, 'content') else str(message)
                    
                    if content.strip().lower() == user_message.strip().lower():
                        continue
                        
                    yield f"data: {json.dumps({'type': 'message', 'content': content})}\n\n"
                
                final_result = agent.invoke(inputs, {"recursion_limit": RECURSION_LIMIT})
                conversation_history.clear()
                conversation_history.extend(final_result["messages"])
                
                yield f"data: {json.dumps({'type': 'end'})}\n\n"
                
            except Exception as e:
                logger.error(f"Error in stream: {e}")
                yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
        
        return app.response_class(generate(), mimetype='text/plain')
        
    except Exception as e:
        logger.error(f"Error processing stream: {e}")
        return jsonify({'error': str(e), 'success': False}), 500

@app.route('/api/clear', methods=['POST'])
def clear_history():
    """Clear conversation history"""
    conversation_history.clear()
    logger.info("Conversation history cleared")
    return jsonify({'success': True, 'message': 'History cleared'})

@app.route('/api/status', methods=['GET'])
def status():
    """Check API status"""
    return jsonify({
        'status': 'running',
        'model': os.getenv('MODEL_PROVIDER', 'gemini'),
        'message': 'Terminal Agent is running'
    })

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

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--cli':
        
        from agent import run_cli
        run_cli()
    else:
        print("🚀 Terminal Agent Web Server")
        print("=" * 40)
        
        has_api_key = check_api_key()
        if not has_api_key:
            print("⚠️  Running without API key - limited functionality")
        
        print(f"🌐 Server starting at: http://localhost:{os.getenv('PORT', 5000)}")
        print("🛑 Press Ctrl+C to stop")
        print("=" * 40)
        
        try:
            app.run(
                host=os.getenv('HOST', '0.0.0.0'),
                port=int(os.getenv('PORT', 5000)),
                debug=os.getenv('DEBUG', 'False').lower() == 'true'
            )
        except KeyboardInterrupt:
            print("\n👋 Server stopped")
        except Exception as e:
            print(f"❌ Error: {e}")
            sys.exit(1)