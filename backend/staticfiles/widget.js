/**
 * Business Chatbot Widget
 * Embeddable chat widget for customer websites
 *
 * Usage:
 * <script src="http://your-domain/static/widget.js" data-widget-key="YOUR_WIDGET_KEY"></script>
 */

(function() {
  'use strict';

  // Configuration - dynamically determine API URL from script source
  // This allows the widget to work on any domain where the script is loaded from
  function getApiBaseUrl() {
    // Try to get the URL from the script that loaded this widget
    const scripts = document.querySelectorAll('script[data-widget-key]');
    for (const script of scripts) {
      const src = script.src;
      if (src) {
        // Extract base URL from script source (e.g., https://kribaat.com/api/v1/widget/widget.js -> https://kribaat.com/api/v1)
        const match = src.match(/^(https?:\/\/[^\/]+)\/api\/v1\/widget\/widget\.js/);
        if (match) {
          return `${match[1]}/api/v1`;
        }
      }
    }
    // Fallback for development
    return 'http://localhost:8000/api/v1';
  }
  
  const API_BASE_URL = getApiBaseUrl();
  const WIDGET_STYLES = `
    #chat-widget-container {
      position: fixed;
      z-index: 999999;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    }

    #chat-widget-container.bottom-right {
      bottom: 20px;
      right: 20px;
    }

    #chat-widget-container.bottom-left {
      bottom: 20px;
      left: 20px;
    }

    #chat-widget-button {
      width: 60px;
      height: 60px;
      border-radius: 50%;
      border: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
      transition: transform 0.2s, box-shadow 0.2s;
    }

    #chat-widget-button:hover {
      transform: scale(1.05);
      box-shadow: 0 6px 16px rgba(0, 0, 0, 0.2);
    }

    #chat-widget-button svg {
      width: 28px;
      height: 28px;
      fill: white;
    }

    #chat-widget-window {
      position: absolute;
      bottom: 80px;
      width: 380px;
      height: 550px;
      background: white;
      border-radius: 16px;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
      display: none;
      flex-direction: column;
      overflow: hidden;
    }

    #chat-widget-container.bottom-right #chat-widget-window {
      right: 0;
    }

    #chat-widget-container.bottom-left #chat-widget-window {
      left: 0;
    }

    #chat-widget-window.open {
      display: flex;
    }

    #chat-widget-header {
      padding: 16px;
      color: white;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }

    #chat-widget-header h3 {
      margin: 0;
      font-size: 16px;
      font-weight: 600;
    }

    #chat-widget-header p {
      margin: 4px 0 0 0;
      font-size: 12px;
      opacity: 0.9;
    }

    #chat-widget-close {
      background: none;
      border: none;
      color: white;
      cursor: pointer;
      padding: 4px;
      opacity: 0.8;
      transition: opacity 0.2s;
    }

    #chat-widget-close:hover {
      opacity: 1;
    }

    #chat-widget-messages {
      flex: 1;
      overflow-y: auto;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    .chat-message {
      max-width: 80%;
      padding: 12px 16px;
      border-radius: 16px;
      font-size: 14px;
      line-height: 1.4;
      word-wrap: break-word;
    }

    .chat-message.customer {
      align-self: flex-end;
      background: #3B82F6;
      color: white;
      border-bottom-right-radius: 4px;
    }

    .chat-message.ai,
    .chat-message.human {
      align-self: flex-start;
      background: #f1f5f9;
      color: #1e293b;
      border-bottom-left-radius: 4px;
    }

    .chat-message.system {
      align-self: center;
      background: #fef3c7;
      color: #92400e;
      font-size: 12px;
      padding: 8px 12px;
    }

    .chat-typing {
      align-self: flex-start;
      padding: 12px 16px;
      background: #f1f5f9;
      border-radius: 16px;
      border-bottom-left-radius: 4px;
    }

    .chat-typing-dots {
      display: flex;
      gap: 4px;
    }

    .chat-typing-dots span {
      width: 8px;
      height: 8px;
      background: #94a3b8;
      border-radius: 50%;
      animation: typing 1.4s infinite;
    }

    .chat-typing-dots span:nth-child(2) {
      animation-delay: 0.2s;
    }

    .chat-typing-dots span:nth-child(3) {
      animation-delay: 0.4s;
    }

    @keyframes typing {
      0%, 60%, 100% { transform: translateY(0); }
      30% { transform: translateY(-8px); }
    }

    #chat-widget-input-area {
      padding: 16px;
      border-top: 1px solid #e2e8f0;
      display: flex;
      gap: 8px;
    }

    #chat-widget-input {
      flex: 1;
      padding: 12px 16px;
      border: 1px solid #e2e8f0;
      border-radius: 24px;
      font-size: 14px;
      outline: none;
      transition: border-color 0.2s;
    }

    #chat-widget-input:focus {
      border-color: #3B82F6;
    }

    #chat-widget-send {
      width: 44px;
      height: 44px;
      border-radius: 50%;
      border: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: opacity 0.2s;
    }

    #chat-widget-send:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    #chat-widget-send svg {
      width: 20px;
      height: 20px;
      fill: white;
    }

    #chat-widget-intro {
      padding: 24px;
      text-align: center;
    }

    #chat-widget-intro h4 {
      margin: 0 0 8px 0;
      color: #1e293b;
    }

    #chat-widget-intro p {
      margin: 0;
      color: #64748b;
      font-size: 14px;
    }

    #chat-widget-start-form {
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    #chat-widget-start-form input {
      padding: 12px 16px;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      font-size: 14px;
      outline: none;
    }

    #chat-widget-start-form input:focus {
      border-color: #3B82F6;
    }

    #chat-widget-start-btn {
      padding: 12px 24px;
      border: none;
      border-radius: 8px;
      color: white;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      transition: opacity 0.2s;
    }

    #chat-widget-start-btn:hover {
      opacity: 0.9;
    }

    .chat-widget-badge {
      position: absolute;
      top: -8px;
      right: -8px;
      background: #ef4444;
      color: white;
      width: 24px;
      height: 24px;
      border-radius: 50%;
      font-size: 12px;
      font-weight: 600;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    @media (max-width: 480px) {
      #chat-widget-window {
        width: calc(100vw - 40px);
        height: calc(100vh - 120px);
        bottom: 80px;
      }
    }
  `;

  // Widget State
  let widgetConfig = null;
  let sessionId = null;
  let conversationId = null;
  let isOpen = false;
  let isTyping = false;
  let hasStarted = false;

  // Initialize widget
  function init() {
    const script = document.currentScript || document.querySelector('script[data-widget-key]');
    const widgetKey = script?.getAttribute('data-widget-key');

    if (!widgetKey) {
      console.error('Chat widget: Missing data-widget-key attribute');
      return;
    }

    // Inject styles
    const styleEl = document.createElement('style');
    styleEl.textContent = WIDGET_STYLES;
    document.head.appendChild(styleEl);

    // Fetch widget config and create widget
    fetchWidgetConfig(widgetKey);
  }

  async function fetchWidgetConfig(widgetKey) {
    try {
      const response = await fetch(`${API_BASE_URL}/widget/config/?key=${widgetKey}`);
      if (!response.ok) throw new Error('Failed to fetch widget config');

      widgetConfig = await response.json();
      createWidget();
    } catch (error) {
      console.error('Chat widget: Failed to initialize', error);
    }
  }

  function createWidget() {
    const container = document.createElement('div');
    container.id = 'chat-widget-container';
    container.className = widgetConfig.position || 'bottom-right';

    const color = widgetConfig.color || '#3B82F6';

    container.innerHTML = `
      <button id="chat-widget-button" style="background-color: ${color}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
        </svg>
      </button>

      <div id="chat-widget-window">
        <div id="chat-widget-header" style="background-color: ${color}">
          <div>
            <h3>${widgetConfig.business_name || 'Chat with us'}</h3>
            <p>We typically reply instantly</p>
          </div>
          <button id="chat-widget-close">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>

        <div id="chat-widget-content">
          <div id="chat-widget-intro">
            <h4>👋 Welcome!</h4>
            <p>${widgetConfig.greeting || 'Start a conversation and we\'ll be happy to help you.'}</p>
          </div>

          <form id="chat-widget-start-form">
            <input type="text" id="chat-customer-name" placeholder="Your name (optional)">
            <input type="email" id="chat-customer-email" placeholder="Email (optional)">
            <button type="submit" id="chat-widget-start-btn" style="background-color: ${color}">
              Start Chat
            </button>
          </form>
        </div>

        <div id="chat-widget-chat" style="display: none; flex: 1; flex-direction: column;">
          <div id="chat-widget-messages"></div>

          <div id="chat-widget-input-area">
            <input type="text" id="chat-widget-input" placeholder="Type your message...">
            <button id="chat-widget-send" style="background-color: ${color}">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="22" y1="2" x2="11" y2="13"></line>
                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
              </svg>
            </button>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(container);

    // Event listeners
    document.getElementById('chat-widget-button').addEventListener('click', toggleWidget);
    document.getElementById('chat-widget-close').addEventListener('click', closeWidget);
    document.getElementById('chat-widget-start-form').addEventListener('submit', startChat);
    document.getElementById('chat-widget-input').addEventListener('keypress', handleInputKeypress);
    document.getElementById('chat-widget-send').addEventListener('click', sendMessage);

    // Check for existing session
    const savedSession = localStorage.getItem('chat_widget_session');
    if (savedSession) {
      const session = JSON.parse(savedSession);
      if (session.widgetKey === widgetConfig.widget_key && session.conversationId) {
        sessionId = session.sessionId;
        conversationId = session.conversationId;
        hasStarted = true;
        showChatInterface();
        loadConversation();
      }
    }
  }

  function toggleWidget() {
    if (isOpen) {
      closeWidget();
    } else {
      openWidget();
    }
  }

  function openWidget() {
    isOpen = true;
    document.getElementById('chat-widget-window').classList.add('open');

    if (hasStarted) {
      document.getElementById('chat-widget-input').focus();
    }
  }

  function closeWidget() {
    isOpen = false;
    document.getElementById('chat-widget-window').classList.remove('open');
  }

  async function startChat(e) {
    e.preventDefault();

    const name = document.getElementById('chat-customer-name').value.trim();
    const email = document.getElementById('chat-customer-email').value.trim();

    try {
      // Create session
      const sessionResponse = await fetch(`${API_BASE_URL}/widget/session/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          widget_key: widgetConfig.widget_key,
          customer_name: name || null,
          customer_email: email || null,
        }),
      });

      if (!sessionResponse.ok) throw new Error('Failed to create session');

      const sessionData = await sessionResponse.json();
      sessionId = sessionData.session_id;
      conversationId = sessionData.conversation_id;
      hasStarted = true;

      // Save session
      localStorage.setItem('chat_widget_session', JSON.stringify({
        widgetKey: widgetConfig.widget_key,
        sessionId,
        conversationId,
      }));

      showChatInterface();

      // Show greeting message if configured
      if (widgetConfig.greeting) {
        addMessage('system', widgetConfig.greeting);
      }

    } catch (error) {
      console.error('Chat widget: Failed to start chat', error);
      alert('Failed to start chat. Please try again.');
    }
  }

  function showChatInterface() {
    document.getElementById('chat-widget-content').style.display = 'none';
    document.getElementById('chat-widget-chat').style.display = 'flex';
  }

  async function loadConversation() {
    if (!conversationId) return;

    try {
      const response = await fetch(`${API_BASE_URL}/widget/conversation/${conversationId}/?session_id=${sessionId}`);
      if (!response.ok) throw new Error('Failed to load conversation');

      const data = await response.json();
      const messagesContainer = document.getElementById('chat-widget-messages');
      messagesContainer.innerHTML = '';

      data.messages.forEach(msg => {
        addMessage(msg.sender, msg.content, false);
      });

      scrollToBottom();
    } catch (error) {
      console.error('Chat widget: Failed to load conversation', error);
    }
  }

  function handleInputKeypress(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  async function sendMessage() {
    const input = document.getElementById('chat-widget-input');
    const content = input.value.trim();

    if (!content || !conversationId) return;

    input.value = '';
    input.disabled = true;
    document.getElementById('chat-widget-send').disabled = true;

    // Add customer message to UI
    addMessage('customer', content);

    // Show typing indicator
    showTyping();

    try {
      const response = await fetch(`${API_BASE_URL}/widget/message/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          conversation_id: conversationId,
          content,
        }),
      });

      if (!response.ok) throw new Error('Failed to send message');

      const data = await response.json();

      hideTyping();

      // Add AI/human response to UI
      if (data.response) {
        addMessage(data.response.sender, data.response.content);
      }

      // Handle handoff notification
      if (data.handoff_initiated) {
        addMessage('system', 'A human agent will be with you shortly.');
      }

    } catch (error) {
      console.error('Chat widget: Failed to send message', error);
      hideTyping();
      addMessage('system', 'Failed to send message. Please try again.');
    } finally {
      input.disabled = false;
      document.getElementById('chat-widget-send').disabled = false;
      input.focus();
    }
  }

  function addMessage(sender, content, scroll = true) {
    const messagesContainer = document.getElementById('chat-widget-messages');
    const messageEl = document.createElement('div');
    messageEl.className = `chat-message ${sender}`;
    messageEl.textContent = content;
    messagesContainer.appendChild(messageEl);

    if (scroll) {
      scrollToBottom();
    }
  }

  function showTyping() {
    isTyping = true;
    const messagesContainer = document.getElementById('chat-widget-messages');
    const typingEl = document.createElement('div');
    typingEl.id = 'chat-typing-indicator';
    typingEl.className = 'chat-typing';
    typingEl.innerHTML = `
      <div class="chat-typing-dots">
        <span></span>
        <span></span>
        <span></span>
      </div>
    `;
    messagesContainer.appendChild(typingEl);
    scrollToBottom();
  }

  function hideTyping() {
    isTyping = false;
    const typingEl = document.getElementById('chat-typing-indicator');
    if (typingEl) {
      typingEl.remove();
    }
  }

  function scrollToBottom() {
    const messagesContainer = document.getElementById('chat-widget-messages');
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  // Start initialization when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
