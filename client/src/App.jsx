import { useState, useRef, useEffect } from 'react';
import './App.css';

function App() {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState([
    { sender: 'bot', text: '...' }
  ]);
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const sendMessage = async () => {
    if (!input.trim()) return;

    const userMessage = { sender: 'user', text: input };
    setMessages([...messages, userMessage]);
    setInput('');

    try {
      setLoading(true);
      const res = await fetch('http://127.0.0.1:8080/recommend', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: input })
      });
      const data = await res.json();
      console.log(data.recommendation);
      
      // Check if data.recommendation is an object with anime data
      if (typeof data.recommendation === 'object' && data.recommendation !== null && !Array.isArray(data.recommendation)) {
        const botMessage = { sender: 'bot', recommendations: data.recommendation };
        setMessages((prev) => [...prev, botMessage]);
      } else {
        // Fallback for text responses
        const botMessage = { sender: 'bot', text: data.recommendation };
        setMessages((prev) => [...prev, botMessage]);
      }
    } catch (error) {
      setMessages((prev) => [...prev, { sender: 'bot', text: '❌ Sorry, I encountered an error. Please try again.' }]);
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const AnimeCard = ({ title, animeId, imageUrl, description }) => {
    return (
      <div className="anime-card">
        <div className="anime-image-container">
          <a 
            href={`https://anilist.co/anime/${animeId}`} 
            target="_blank" 
            rel="noopener noreferrer"
            className="anime-link"
          >
            <img 
              src={imageUrl} 
              alt={title}
              className="anime-image"
              onError={(e) => {
                e.target.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTIwIiBoZWlnaHQ9IjE2MCIgdmlld0JveD0iMCAwIDEyMCAxNjAiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxyZWN0IHdpZHRoPSIxMjAiIGhlaWdodD0iMTYwIiBmaWxsPSIjM0EzQTM5Ii8+Cjx0ZXh0IHg9IjYwIiB5PSI4MCIgZmlsbD0iI0Y5Qzg0NSIgZm9udC1mYW1pbHk9IkFyaWFsIiBmb250LXNpemU9IjE0IiB0ZXh0LWFuY2hvcj0ibWlkZGxlIj5ObyBJbWFnZTwvdGV4dD4KPC9zdmc+';
              }}
            />
          </a>
          <div className="anime-tooltip">
            <div dangerouslySetInnerHTML={{ __html: description }} />
          </div>
        </div>
        <h4 className="anime-title">{title}</h4>
      </div>
    );
  };

  return (
    <div className="chat-app">
      {/* Header */}
      <div className="chat-header">
        <div className="header-content">
          <div className="bot-avatar">
            <img src="/Elizabeth_AI_in_Minimalist_Style-ai-brush-removebg-awqmls8c.png" alt="Anime Assistant" />
          </div>
          <h1>Elizabeth AI</h1>
          <div className="status-indicator"></div>
        </div>
      </div>

      {/* Chat Messages */}
      <div className="chat-messages">
        {messages.map((msg, i) => (
          <div key={i} className={`message-container ${msg.sender}`}>
            <div className="message-avatar">
              {msg.sender === 'bot' ? (
                <img src="/caption-elizabeth-the-mysterious-comrade-of-gintama-m8b59ru86t9907h3.jpg" alt="Bot" />
              ) : (
                <img src="/_ (1).jpeg" alt="User" />
              )}
            </div>
            <div className={`message-bubble ${msg.sender}`}>
              {msg.text && msg.text}
              {msg.recommendations && (
                <div className="recommendations-container">
                  
                  <div className="anime-grid">
                    {Object.entries(msg.recommendations).map(([title, details], index) => (
                      <AnimeCard
                        key={`${details[0]}-${index}`}
                        title={title}
                        animeId={details['id']}
                        imageUrl={details['image']}
                        description={details['description']}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="message-container bot">
            <div className="message-avatar">🤖</div>
            <div className="message-bubble bot">
              <div className="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
                <span className="typing-text">Thinking...</span>
              </div>
            </div>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="chat-input-container">
        <div className="input-wrapper">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Ask me about anime recommendations..."
            disabled={loading}
            rows={1}
          />
          <button
            onClick={sendMessage}
            disabled={loading || !input.trim()}
            className="send-button"
          >
            {loading ? (
              <div className="loading-spinner"></div>
            ) : (
              <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                <path d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            )}
          </button>
        </div>
        <p className="input-hint">Press Enter to send, Shift + Enter for new line</p>
      </div>
    </div>
  );
}

export default App;