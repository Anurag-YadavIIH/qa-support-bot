# test_ui.py
# An interactive chat-style Flask page for manually testing the QA Support Bot API.
# Run the FastAPI server first (uvicorn app.main:app --port 8000),
# then run this: python test_ui.py
# Open http://localhost:5000 in a browser.

import os

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template_string, request

load_dotenv()

app = Flask(__name__)

API_BASE = "http://localhost:8000"
DEFAULT_URL = os.getenv("TARGET_URL", "")
DEFAULT_MAX_PAGES = os.getenv("MAX_PAGES", "10")

PAGE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>QA Support Bot</title>
  <style>
    * { box-sizing: border-box; }
    body {
      font-family: 'Segoe UI', system-ui, sans-serif;
      margin: 0;
      min-height: 100vh;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 20px;
    }
    .chat-card {
      width: 100%;
      max-width: 720px;
      background: #ffffff;
      border-radius: 16px;
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.25);
      overflow: hidden;
      display: flex;
      flex-direction: column;
      height: 80vh;
    }
    .chat-header {
      background: linear-gradient(135deg, #667eea, #764ba2);
      color: white;
      padding: 18px 24px;
    }
    .chat-header h1 { margin: 0; font-size: 20px; }
    .chat-header p { margin: 4px 0 0; font-size: 13px; opacity: 0.85; }
    .chat-messages {
      flex: 1;
      padding: 20px;
      overflow-y: auto;
      background: #f4f5fb;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }
    .bubble {
      max-width: 80%;
      padding: 12px 16px;
      border-radius: 16px;
      line-height: 1.45;
      font-size: 14.5px;
      animation: pop 0.2s ease;
    }
    @keyframes pop {
      from { opacity: 0; transform: translateY(6px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .bubble.user {
      align-self: flex-end;
      background: linear-gradient(135deg, #667eea, #764ba2);
      color: white;
      border-bottom-right-radius: 4px;
    }
    .bubble.bot {
      align-self: flex-start;
      background: white;
      color: #1f2330;
      border: 1px solid #e3e5f0;
      border-bottom-left-radius: 4px;
    }
    .bubble.bot.empty {
      color: #8a8fa3;
      font-style: italic;
    }
    .sources {
      margin-top: 8px;
      font-size: 12px;
      color: #6b6f85;
    }
    .sources a { color: #5d5fef; text-decoration: none; word-break: break-all; }
    .sources a:hover { text-decoration: underline; }
    .typing {
      align-self: flex-start;
      display: flex;
      gap: 4px;
      padding: 12px 16px;
      background: white;
      border: 1px solid #e3e5f0;
      border-radius: 16px;
    }
    .typing span {
      width: 7px; height: 7px;
      background: #b0b3c4;
      border-radius: 50%;
      animation: bounce 1.2s infinite;
    }
    .typing span:nth-child(2) { animation-delay: 0.15s; }
    .typing span:nth-child(3) { animation-delay: 0.3s; }
    @keyframes bounce {
      0%, 80%, 100% { transform: translateY(0); opacity: 0.5; }
      40% { transform: translateY(-5px); opacity: 1; }
    }
    .chat-input {
      display: flex;
      gap: 10px;
      padding: 16px;
      background: white;
      border-top: 1px solid #eceef5;
    }
    .chat-input textarea {
      flex: 1;
      resize: none;
      border: 1px solid #d8dae8;
      border-radius: 12px;
      padding: 10px 14px;
      font-size: 14.5px;
      font-family: inherit;
      height: 44px;
      outline: none;
    }
    .chat-input textarea:focus { border-color: #764ba2; }
    .chat-input button {
      background: linear-gradient(135deg, #667eea, #764ba2);
      color: white;
      border: none;
      border-radius: 12px;
      padding: 0 22px;
      font-size: 14.5px;
      font-weight: 600;
      cursor: pointer;
      transition: transform 0.1s ease, opacity 0.2s ease;
    }
    .chat-input button:hover { opacity: 0.92; }
    .chat-input button:active { transform: scale(0.97); }
    .chat-input button:disabled { opacity: 0.5; cursor: not-allowed; }
    .hint {
      text-align: center;
      font-size: 12px;
      color: #9296a8;
      padding: 6px 0 0;
    }
    .source-bar {
      background: #ecebfb;
      border-bottom: 1px solid #ddd9f7;
      padding: 10px 18px;
      font-size: 13px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      flex-wrap: wrap;
    }
    .source-bar .current {
      color: #463f8c;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .source-bar .current strong { color: #2c2566; }
    .source-bar button {
      background: white;
      border: 1px solid #c8c3f0;
      color: #5d5fef;
      border-radius: 8px;
      padding: 5px 12px;
      font-size: 12.5px;
      font-weight: 600;
      cursor: pointer;
      white-space: nowrap;
    }
    .source-bar button:hover { background: #f4f3ff; }
    .source-panel {
      display: none;
      background: white;
      border-bottom: 1px solid #eceef5;
      padding: 14px 18px;
      gap: 10px;
      flex-direction: column;
    }
    .source-panel.open { display: flex; }
    .source-panel label {
      font-size: 12px;
      font-weight: 600;
      color: #555;
    }
    .source-panel input {
      width: 100%;
      padding: 8px 10px;
      border: 1px solid #d8dae8;
      border-radius: 8px;
      font-size: 14px;
      margin-top: 4px;
    }
    .source-panel .row { display: flex; gap: 10px; }
    .source-panel .row > div { flex: 1; }
    .source-panel .row > div:last-child { max-width: 120px; }
    .source-panel .actions {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-top: 4px;
    }
    .source-panel .actions button {
      background: linear-gradient(135deg, #667eea, #764ba2);
      color: white;
      border: none;
      border-radius: 8px;
      padding: 8px 18px;
      font-size: 13.5px;
      font-weight: 600;
      cursor: pointer;
    }
    .source-panel .actions button:disabled { opacity: 0.5; cursor: not-allowed; }
    .source-status {
      font-size: 12.5px;
      color: #6b6f85;
    }
    .source-status.error { color: #b00020; }
    .source-status.success { color: #1a8a4a; }
  </style>
</head>
<body>
  <div class="chat-card">
    <div class="chat-header">
      <h1>QA Support Bot</h1>
      <p>Ask me anything from the crawled documentation — I only answer from what I've read.</p>
    </div>
    <div class="source-bar">
      <div class="current">Indexed site: <strong id="currentSite">{{ default_url or "not set" }}</strong></div>
      <button onclick="toggleSourcePanel()">Change site / field of interest</button>
    </div>
    <div class="source-panel" id="sourcePanel">
      <div class="row">
        <div>
          <label>Website URL to crawl</label>
          <input id="sourceUrl" type="text" placeholder="https://example.com/docs/" value="{{ default_url or '' }}">
        </div>
        <div>
          <label>Max pages</label>
          <input id="sourceMaxPages" type="number" min="1" max="100" value="{{ default_max_pages }}">
        </div>
      </div>
      <div class="actions">
        <button id="reindexBtn" onclick="reindex()">Crawl &amp; Re-index</button>
        <span class="source-status" id="sourceStatus"></span>
      </div>
    </div>
    <div class="chat-messages" id="messages">
      <div class="bubble bot">Hi! Ask me a question about the indexed content — for example, "What is a Python list?"</div>
    </div>
    <div class="chat-input">
      <textarea id="question" placeholder="Type your question..." rows="1"></textarea>
      <button id="sendBtn" onclick="sendQuestion()">Ask</button>
    </div>
    <div class="hint">Press Enter to send, Shift+Enter for a new line</div>
  </div>

  <script>
    const messages = document.getElementById('messages');
    const input = document.getElementById('question');
    const sendBtn = document.getElementById('sendBtn');

    function escapeHtml(str) {
      const div = document.createElement('div');
      div.textContent = str;
      return div.innerHTML;
    }

    function addBubble(text, sender, sources) {
      const div = document.createElement('div');
      div.className = 'bubble ' + sender;
      div.innerHTML = escapeHtml(text);
      if (sources && sources.length > 0) {
        const src = document.createElement('div');
        src.className = 'sources';
        src.innerHTML = '<strong>Sources:</strong><br>' +
          sources.map(s => `<a href="${s}" target="_blank">${escapeHtml(s)}</a>`).join('<br>');
        div.appendChild(src);
      }
      messages.appendChild(div);
      messages.scrollTop = messages.scrollHeight;
    }

    function showTyping() {
      const div = document.createElement('div');
      div.className = 'typing';
      div.id = 'typingIndicator';
      div.innerHTML = '<span></span><span></span><span></span>';
      messages.appendChild(div);
      messages.scrollTop = messages.scrollHeight;
    }

    function hideTyping() {
      const el = document.getElementById('typingIndicator');
      if (el) el.remove();
    }

    async function sendQuestion() {
      const question = input.value.trim();
      if (question.length < 3) return;

      addBubble(question, 'user');
      input.value = '';
      sendBtn.disabled = true;
      showTyping();

      try {
        const res = await fetch('/api/ask', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question })
        });
        const data = await res.json();
        hideTyping();

        if (data.error) {
          addBubble(data.error, 'bot empty');
        } else {
          addBubble(data.answer, 'bot', data.sources);
        }
      } catch (err) {
        hideTyping();
        addBubble('Something went wrong talking to the API: ' + err, 'bot empty');
      } finally {
        sendBtn.disabled = false;
        input.focus();
      }
    }

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendQuestion();
      }
    });

    const sourcePanel = document.getElementById('sourcePanel');
    const reindexBtn = document.getElementById('reindexBtn');
    const sourceStatus = document.getElementById('sourceStatus');
    const currentSite = document.getElementById('currentSite');

    function toggleSourcePanel() {
      sourcePanel.classList.toggle('open');
    }

    async function reindex() {
      const url = document.getElementById('sourceUrl').value.trim();
      const maxPages = parseInt(document.getElementById('sourceMaxPages').value, 10) || 10;

      if (!url) {
        sourceStatus.textContent = 'Enter a website URL first.';
        sourceStatus.className = 'source-status error';
        return;
      }

      reindexBtn.disabled = true;
      sourceStatus.textContent = 'Crawling and indexing... this can take 1-3 minutes.';
      sourceStatus.className = 'source-status';

      try {
        const res = await fetch('/api/ingest', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url, max_pages: maxPages })
        });
        const data = await res.json();

        if (data.error) {
          sourceStatus.textContent = data.error;
          sourceStatus.className = 'source-status error';
        } else {
          sourceStatus.textContent = `Indexed ${data.pages_crawled} pages from ${url}.`;
          sourceStatus.className = 'source-status success';
          currentSite.textContent = url;
          messages.innerHTML = '';
          addBubble(`Knowledge base updated — now indexed from ${url} (${data.pages_crawled} pages). Ask me something about it!`, 'bot');
          sourcePanel.classList.remove('open');
        }
      } catch (err) {
        sourceStatus.textContent = 'Request failed: ' + err;
        sourceStatus.className = 'source-status error';
      } finally {
        reindexBtn.disabled = false;
      }
    }
  </script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(PAGE, default_url=DEFAULT_URL, default_max_pages=DEFAULT_MAX_PAGES)


@app.route("/api/ask", methods=["POST"])
def api_ask():
    question = (request.json or {}).get("question", "").strip()
    if len(question) < 3:
        return jsonify({"error": "Question must be at least 3 characters."})

    try:
        response = requests.post(f"{API_BASE}/ask", json={"question": question}, timeout=30)
        response.raise_for_status()
        data = response.json()
        return jsonify({"answer": data["answer"], "sources": data["sources"]})
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Could not connect to the API. Is it running on http://localhost:8000?"})
    except Exception as e:
        return jsonify({"error": f"Request failed: {e}"})


@app.route("/api/ingest", methods=["POST"])
def api_ingest():
    body = request.json or {}
    url = body.get("url", "").strip()
    max_pages = body.get("max_pages")

    if not url:
        return jsonify({"error": "A website URL is required."})

    try:
        response = requests.post(
            f"{API_BASE}/ingest",
            json={"url": url, "max_pages": max_pages},
            timeout=300,  # crawling + embedding can take a few minutes
        )
        response.raise_for_status()
        data = response.json()
        return jsonify({"pages_crawled": data["pages_crawled"]})
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Could not connect to the API. Is it running on http://localhost:8000?"})
    except requests.exceptions.HTTPError:
        try:
            detail = response.json().get("detail", response.text)
        except Exception:
            detail = response.text
        return jsonify({"error": f"Ingestion failed: {detail}"})
    except Exception as e:
        return jsonify({"error": f"Request failed: {e}"})


if __name__ == "__main__":
    app.run(port=5000, debug=True)
