# Elizabeth AI - Anime Recommendation Agent

![Elizabeth AI](client/public/Elizabeth_AI_in_Minimalist_Style-ai-brush-removebg-awqmls8c.png)

Elizabeth AI is a smart, conversational anime recommendation assistant that helps you discover anime you'll love based on your preferences — powered by large language models and enriched with the [AniList MCP Server](https://github.com/yuna0x0/anilist-mcp) and Linkup Websearch tool.

> Inspired by Elizabeth from *Gintama* — cryptic on the outside, deeply insightful on the inside.

---

## 💡 Features

- 🎯 **Refines recommendations** — based on your genre, tone, characters, or art-style preferences  
- 🔍 **Uses AniList MCP Server** — for accurate anime metadata, ratings, and tags
- 🧠 **Context-aware responses** — considers previous conversation history for better suggestions
- 🌐 **Web Search Support** – When AniList alone won’t cut it, Elizabeth taps into web results to stay up to date.
- ✨ **Customizable output format** — clear, ranked, and formatted anime suggestions

---

## 🛠️ Tech Stack

- **Frontend**: React.js  
- **Backend**: Flask (Python)  
- **AI Model**: OpenAI GPT-4o-mini (via OpenAI SDK)  
- **External API**: AniList GraphQL and Linkup Websearch
- **Agent Framework**: OpenAI Agents SDK  

---


## Examples 

![Eg_1](client/public/ex1.png)
![Eg_2](client/public/ex4.png)

## 🚀 How to Run Locally

1. **Clone the Repo**
   ```bash
   git clone https://github.com/guhan-tofu/AI-Anime-Rec.git
   cd Elizabeth-AI

   # For backend
   cd flask-server
   python main.py

   # For frontend
   cd client
   npm run dev
