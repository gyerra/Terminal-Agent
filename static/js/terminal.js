let isProcessing = false;
let currentStream = null;

// Initialize
document.addEventListener('DOMContentLoaded', function() {
    checkStatus();
    setupEventListeners();
});

function setupEventListeners() {
    const input = document.getElementById('commandInput');
    const sendBtn = document.getElementById('sendBtn');

    input.addEventListener('keypress', function(e) {
        if (e.key === 'Enter' && !isProcessing) {
            sendMessage();
        }
    });

    input.addEventListener('input', function() {
        sendBtn.disabled = !this.value.trim() || isProcessing;
    });

    // Add keyboard shortcuts
    document.addEventListener('keydown', function(e) {
        // Ctrl+L to clear terminal
        if (e.ctrlKey && e.key === 'l') {
            e.preventDefault();
            clearHistory();
        }
        
        // Ctrl+K to clear input
        if (e.ctrlKey && e.key === 'k') {
            e.preventDefault();
            document.getElementById('commandInput').value = '';
        }
    });
}

async function checkStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        updateStatusIndicator(true);
    } catch (error) {
        updateStatusIndicator(false);
        console.error('Status check failed:', error);
    }
}

function updateStatusIndicator(online) {
    const indicator = document.getElementById('statusIndicator');
    if (indicator) {
        indicator.className = `status-indicator ${online ? 'status-online' : 'status-offline'}`;
    }
}

async function sendMessage() {
    const input = document.getElementById('commandInput');
    const message = input.value.trim();
    
    if (!message || isProcessing) return;

    isProcessing = true;
    input.disabled = true;
    document.getElementById('sendBtn').disabled = true;

    // Add user message to output
    addMessage(message, 'user');

    // Clear input
    input.value = '';

    try {
        // Start streaming response
        await streamResponse(message);
    } catch (error) {
        addMessage(`Error: ${error.message}`, 'error');
        console.error('Stream error:', error);
    } finally {
        isProcessing = false;
        input.disabled = false;
        document.getElementById('sendBtn').disabled = false;
        input.focus();
    }
}

async function streamResponse(message) {
    const response = await fetch('/api/stream', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ message: message })
    });

    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let aiMessageDiv = null;
    let isFirstChunk = true;

    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        
                        if (data.type === 'message') {
                            if (isFirstChunk) {
                                aiMessageDiv = addMessage('', 'ai');
                                isFirstChunk = false;
                            }
                            aiMessageDiv.textContent += data.content;
                            scrollToBottom();
                        } else if (data.type === 'error') {
                            addMessage(`Error: ${data.content}`, 'error');
                        } else if (data.type === 'end') {
                            // Stream ended
                        }
                    } catch (e) {
                        console.error('Error parsing stream data:', e);
                    }
                }
            }
        }
    } finally {
        reader.releaseLock();
    }
}

function addMessage(content, type) {
    const output = document.getElementById('terminalOutput');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}-message`;
    
    // Handle different content types
    if (type === 'ai' && content.includes('```')) {
        // Format code blocks
        messageDiv.innerHTML = formatCodeBlocks(content);
    } else {
        messageDiv.textContent = content;
    }
    
    output.appendChild(messageDiv);
    scrollToBottom();
    return messageDiv;
}

function formatCodeBlocks(content) {
    // Simple code block formatting
    return content
        .replace(/```(\w+)?\n([\s\S]*?)```/g, '<pre class="code-block"><code>$2</code></pre>')
        .replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');
}

function scrollToBottom() {
    const output = document.getElementById('terminalOutput');
    output.scrollTop = output.scrollHeight;
}

async function clearHistory() {
    try {
        const response = await fetch('/api/clear', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });
        
        if (response.ok) {
            const output = document.getElementById('terminalOutput');
            output.innerHTML = `
                <div class="message ai-message">
                    Conversation history cleared. How can I help you today?
                </div>
            `;
        } else {
            throw new Error('Failed to clear history');
        }
    } catch (error) {
        console.error('Error clearing history:', error);
        addMessage(`Error clearing history: ${error.message}`, 'error');
    }
}

// Auto-focus input on page load
window.addEventListener('load', function() {
    const input = document.getElementById('commandInput');
    if (input) {
        input.focus();
    }
});

// Handle page visibility changes
document.addEventListener('visibilitychange', function() {
    if (!document.hidden) {
        // Page became visible, check status
        checkStatus();
    }
});

// Handle window focus
window.addEventListener('focus', function() {
    checkStatus();
});

// Export functions for global access
window.TerminalAgent = {
    sendMessage,
    clearHistory,
    checkStatus,
    addMessage
}; 