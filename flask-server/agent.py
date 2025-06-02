from agents.mcp import MCPServerStdio
import asyncio
import os 
import shutil
from agents import Agent, Runner, function_tool, set_default_openai_key, gen_trace_id, handoff
from dotenv import load_dotenv
import json
import requests
from linkup import LinkupClient
from datetime import datetime
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX


class AnimeChatBot:
    def __init__(self):
        self.load_environment()
        self.setup_clients()
        self.load_tags()
        self.server = None
        self.main_agent = None
        self.conversation_history = []
        self.user_preferences = {}

    def load_environment(self):
        load_dotenv()
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.linkup_key = os.getenv("LINKUP_API_KEY")

    def setup_clients(self):
        self.linkup_client = LinkupClient(api_key=self.linkup_key)

    def load_tags(self):
        with open('tags.json', 'r') as file:
            tags = json.load(file)

        self.all_tags = [
            tag["name"] for tag in tags["data"]["MediaTagCollection"] 
            if not tag.get("isAdult", False)
        ]

    def parse_anime_response(self, raw_json):
        media = raw_json.get("data", {}).get("Media", {})
        title_data = media.get("title", {})
        title = title_data.get("english") or title_data.get("romaji", "Unknown Title")
        raw_desc = media.get("description", "")
        description = raw_desc.replace("<br><br>", "\n").split("\n")[0].strip()
        genres = media.get("genres", [])
        tags = [tag["name"] for tag in media.get("tags", [])][:5]
        start = media.get("startDate", {})
        start_date = f"{start.get('year', '??')}-{str(start.get('month', '??')).zfill(2)}-{str(start.get('day', '??')).zfill(2)}"
        country = media.get("countryOfOrigin", "Unknown")
        duration = media.get("duration", 0)
        episodes = media.get("episodes", 0)

        recommendations = []
        for edge in media.get("recommendations", {}).get("edges", []):
            node = edge.get("node", {})
            rec_media = node.get("mediaRecommendation", {})
            title_obj = rec_media.get("title", {})
            english_title = title_obj.get("english")
            if english_title:
                recommendations.append({
                    "title": english_title,
                    "score": node.get("rating", 0),
                    "genres": rec_media.get("genres", [])
                })

        return {
            "title": title,
            "description": description,
            "start_date": start_date,
            "country_of_origin": country,
            "duration_minutes": duration,
            "episodes": episodes,
            "genres": genres,
            "tags": tags,
            "top_recommendations": recommendations
        }

    def create_tools(self):
        @function_tool
        async def get_tags() -> list:
            return self.all_tags

        @function_tool
        async def get_anime_search(id: int) -> dict:
            query = """
            query ($id: Int) {
              Media(id: $id, type: ANIME) {
                title { romaji english }
                startDate { day month year }
                countryOfOrigin
                genres
                duration
                episodes
                tags { name }
                description(asHtml: false)
                recommendations(perPage: 10, sort: RATING_DESC) {
                  edges {
                    node {
                      rating
                      mediaRecommendation {
                        title { english }
                        genres
                      }
                    }
                  }
                }
              }
            }
            """
            variables = {"id": id}
            url = 'https://graphql.anilist.co'
            response = requests.post(url, json={'query': query, 'variables': variables})
            return self.parse_anime_response(response.json())

        @function_tool
        async def search_web(query: str) -> str:
            response = await self.linkup_client.async_search(
                query=query,
                depth='standard',
                output_type='searchResults'
            )
            answer = f"Search results for '{query}' on {datetime.now().strftime('%Y-%m-%d')}\n\n"
            for result in response.results[:3]:
                answer += f"{result.name}\n{result.url}\n{result.content}\n\n"
            return answer

        return get_tags, get_anime_search, search_web

    async def initialize_agents(self):
        if not self.server:
            raise Exception("MCP Server not initialized. Call start_server() first.")

        get_tags, get_anime_search, search_web = self.create_tools()

        anime_anilist_agent = Agent(
            name="Anime Recommender",
            model="gpt-4o-mini",
            instructions=(
                "You are an intelligent anime recommendation agent.\n"
                "Your job is to understand user preferences and use the available AniList tools to recommend relevant anime.\n"
                "\n"
                "CRITICAL: Always start by using misc tools when dealing with genres or tags:\n"
                "- Use `get_genres` to retrieve all available genres on AniList before searching\n"
                "- Use `get_tags` (not part of the mcp server) to retrieve all available tags on AniList before searching\n"
                "- DO NOT use `get_media_tags` - ignore this tool completely\n"
                "- NEVER assume or invent genre names or tags - always verify they exist first\n"
                "- Only use genres and tags that are returned by these tools. DO NOT use terms\n"
                "\n"
                "Search and Discovery Tools:\n"
                "- Use `search_anime` with proper filters (genres, tags, popularity, year, etc.) based on verified genres/tags\n"
                "- Use `search_manga` if the user asks about manga recommendations\n"
                "- Use `search_character` to find characters and their associated anime\n"
                "- Use `search_staff` to find staff members and their work\n"
                "- Use `search_studio` to find studios and their productions\n"
                "\n"
                "Detailed Information Tools:\n"
                "- Use `get_anime_search` (not part of the mcp server) to retrieve detailed info about specific anime (title, description, genres, etc.)\n"
                "- DO NOT use `get_anime` - ignore this tool completely\n"
                "- Use `get_manga` for detailed manga information\n"
                "- Use `get_character` for character details and their anime appearances\n"
                "- Use `get_staff` for staff member details and their work\n"
                "- Use `get_studio` for studio information and their productions\n"
                "\n"
                "Recommendation Tools:\n"
                "- Use `get_recommendations_for_media` to find anime similar to a specific title\n"
                "- Use `get_recommendation` to get specific recommendation details\n"
                "\n"
                "Special Features:\n"
                "- Use `get_todays_birthday_characters` or `get_todays_birthday_staff` for birthday-related queries\n"
                "\n"
                "Workflow Guidelines:\n"
                "1. If user mentions genres/tags, FIRST use `get_genres` and `get_media_tags` to verify they exist\n"
                "2. For vague requests, reason through them step-by-step using multiple tools\n"
                "3. Cross-reference information using different tools for comprehensive recommendations\n"
                "4. If user mentions a character/staff member, find their associated anime through character/staff tools\n"
                "\n"
                "Output Requirements:\n"
                "- Provide helpful and conversational responses\n"
                "- When giving recommendations, include up to 3 anime titles that best match the user's request\n"
                "- Assign each title a score out of 10 based on relevance to the request\n"
                "- Only return the anime title and its score. Do not include explanations, links, or additional commentary. \n"
                "- NEVER invent anime titles - only use results from AniList tools\n"
                "- Format recommendations as: 'Title Name - Score/10'\n"
                "- Be conversational and friendly in your responses\n"
                "- Ask follow-up questions when appropriate to better understand preferences"
                """
                When recommending anime, follow this format:

                1. **Anime Title** – Rating/10  
                2. **Anime Title** – Rating/10  
                3. **Anime Title** – Rating/10

                """
            ),
            mcp_servers=[self.server],
            tools=[get_tags, get_anime_search]
        )

        web_search_agent = Agent(
            name="Web Search Agent",
            model="gpt-4o-mini",
            instructions=( 
                "You are a web search agent focused on anime recommendations.\n "
            "When given a user query, your job is to search the web using the `search_web` tool \n"
            "and return exactly 3 anime recommendations that are the closest match to the user's request.\n "
            "For each anime you recommend, assign a score out of 10 that reflects how well it matches "
            "the user's description, based on the content of the search results. \n"
            "Only return the anime title and its score. Do not include explanations, links, or additional commentary.\n "
            "Only use either the romaji or english title, never both. Always use the anime's base name and never include the season or part name (Eg: Instead of 'Attack on Titan Final Season' use 'Attack on Titan') or (Eg: Instead of 'Boku dake ga Inai Machi(ERASED) just use ERASED') \n\n"
            "- Format recommendations as: 'Title Name - Score/10'\n"
            "Use the search tool only once per request and be as accurate as possible based on the search content."
            """
            When recommending anime, follow this format:

            1. **Anime Title** – Rating/10  
            2. **Anime Title** – Rating/10  
            3. **Anime Title** – Rating/10

            Use only the **official English title** of the anime. Do not include the Japanese or Romaji title, even in parentheses. For example, say **Erased**, not **Boku dake ga Inai Machi** or **Boku dake ga Inai Machi (Erased)**.

            """
            ),
            tools=[search_web]
        )

        self.main_agent = Agent(
            name="Anime Recommender Main Agent",
            model="gpt-4o-mini",
            instructions=RECOMMENDED_PROMPT_PREFIX + (
            "You are an anime recommendation orchestrator. "
            "You manage two specialized agents:\n"
            "- `anime_anilist_agent` (AniList-based recommendations)\n"
            "- `web_search_agent` (web-based recommendations for highly specific or niche cases)\n\n"
            "Always read and consider the entire previous conversation history before responding. Use it to maintain context, avoid repeating information, and build coherent, relevant, and helpful answers that align with the user's earlier questions, preferences, and goals.\n\n"

            "Decision and Handoff Logic:\n"
            "- If the user's query is general or popular (e.g., 'anime like Cowboy Bebop', 'best fantasy romance anime'), use a **handoff to anime_anilist_agent**.\n"
            "- If the user's query is very specific, nuanced, or depends on real-world or trending knowledge (e.g., 'anime with frogs that run a tea shop'), use a **handoff to web_search_agent**.\n"
            "- If the query is multi-faceted or ambiguous and could benefit from both structured data and web context, use **both agents as tools** in parallel.\n"
            "- In the case of **both agents as tools** in parallel, DO NOT use both agents multiple times for the same query. Instead, use each agent once and combine their outputs.\n" 
            "- DO NOT use either agent as a tool by itself — only use tools when **both agents are needed together**.\n\n"

            "Output Requirements:\n"
            "- Return up to 3 anime titles that best match the user's request\n"
            "- Assign each title a score out of 10 based on relevance to the request\n"
            "- Only return the anime title and its score. Do not include explanations, links, or additional commentary. "
            "- NEVER invent anime titles — only use results from AniList or Web Search tools\n"
            "- Format: 'Title Name – Score/10'\n"
            "- Do not include extra commentary beyond the scored recommendations"
            """When recommending anime, follow this format:

                1. **Anime Title** – Rating/10  
                2. **Anime Title** – Rating/10  
                3. **Anime Title** – Rating/10

                Use only the **official English title** of the anime. Do not include the Japanese or Romaji title, even in parentheses. For example, say **Erased**, not **Boku dake ga Inai Machi** or **Boku dake ga Inai Machi (Erased)**.
            """
            ),
            tools=[
                web_search_agent.as_tool(
                    tool_name="web_search_agent",
                    tool_description="Searches the web for anime recommendations."
                ),
                anime_anilist_agent.as_tool(
                    tool_name="anime_anilist_agent",
                    tool_description="Recommends anime using AniList tools."
                )
            ],
            handoffs=[anime_anilist_agent, web_search_agent],
            handoff_description=(
            "Use the anime_anilist_agent for general or popular anime recommendation queries. (e.g., 'anime like Cowboy Bebop', 'best fantasy romance anime')\n"
            "Use the web_search_agent when the query is unusually specific or too niche. (e.g., 'anime with frogs that run a tea shop') "
            )
        )

    async def start_server(self):
        if not shutil.which("npx"):
            raise Exception("npx is not installed. Please install Node.js and try again.")

        self.server = MCPServerStdio(
            name="Anilist Server",
            params={"command": "npx", "args": ["-y", "anilist-mcp"]},
            cache_tools_list=True
        )
        await self.server.__aenter__()
        await self.initialize_agents()
        tools = await self.server.list_tools()
        print(f"✅ Server started with tools: {[tool.name for tool in tools]}")

    async def stop_server(self):
        if self.server:
            await self.server.__aexit__(None, None, None)
            self.server = None
            self.main_agent = None

    def build_context_aware_input(self, current_input: str) -> str:
        context_parts = []
        if self.conversation_history:
            context_parts.append("CONVERSATION HISTORY:")
            for exchange in self.conversation_history[-3:]:
                context_parts.append(f"User: {exchange['user']}")
                context_parts.append(f"Bot: {exchange['bot']}")
        if self.user_preferences:
            context_parts.append("USER PREFERENCES:")
            for key, value in self.user_preferences.items():
                context_parts.append(f"- {key}: {value}")
        context_parts.append(f"CURRENT REQUEST: {current_input}")
        return "\n".join(context_parts)

    def extract_preferences(self, user_input: str, bot_response: str):
        user_lower = user_input.lower()
        genres = ['action', 'romance', 'comedy', 'drama', 'fantasy', 'sci-fi', 'thriller', 'horror', 'slice of life']
        for genre in genres:
            if genre in user_lower and any(x in user_lower for x in ['like', 'love', 'enjoy']):
                self.user_preferences[f'likes_{genre}'] = True
            elif genre in user_lower and any(x in user_lower for x in ['hate', 'dislike', "don't like"]):
                self.user_preferences[f'dislikes_{genre}'] = True
        if 'short' in user_lower or 'few episodes' in user_lower:
            self.user_preferences['prefers_short_series'] = True
        elif 'long' in user_lower or 'many episodes' in user_lower:
            self.user_preferences['prefers_long_series'] = True
        if 'subtitles' in user_lower or 'sub' in user_lower:
            self.user_preferences['prefers_subtitles'] = True
        elif 'dub' in user_lower or 'english' in user_lower:
            self.user_preferences['prefers_dubbed'] = True

    async def get_recommendation(self, user_input: str) -> str:
        if not self.main_agent:
            raise Exception("Agents not initialized. Call start_server() first.")
        try:
            trace_id = gen_trace_id()
            print(f"🔍 Processing request... (Trace: https://platform.openai.com/traces/{trace_id})")
            context_input = self.build_context_aware_input(user_input)
            result = await Runner.run(starting_agent=self.main_agent, input=context_input)
            bot_response = result.final_output
            self.conversation_history.append({'user': user_input, 'bot': bot_response, 'timestamp': datetime.now().isoformat()})
            self.extract_preferences(user_input, bot_response)
            return bot_response
        except Exception as e:
            return f"❌ Error: {str(e)}"

    def clear_context(self):
        self.conversation_history = []
        self.user_preferences = {}
        print("🧹 Conversation context cleared!")

    def show_preferences(self):
        if not self.user_preferences:
            print("🤷 No preferences learned yet.")
            return
        print("🎯 Your learned preferences:")
        for key, value in self.user_preferences.items():
            formatted = key.replace('_', ' ').title()
            print(f"   • {formatted}: {value}")

    async def chat(self):
        print("🎌 Anime Recommendation Chat Bot\n" + "=" * 50)
        print("Starting up the bot... Please wait.")
        try:
            await self.start_server()
            print("✅ Bot is ready! Type your anime requests below.")
            print("💡 Examples:\n - 'anime like Attack on Titan'\n - 'romantic comedy anime'\n")
            while True:
                try:
                    user_input = input("🎯 You: ").strip()
                    if not user_input:
                        print("💭 Please enter your anime request.")
                        continue
                    if user_input.lower() in ['quit', 'exit', 'bye', 'stop']:
                        print("👋 Thanks for using the Anime Chat Bot! Goodbye!")
                        break
                    print("🤖 Bot: Processing your request...")
                    recommendation = await self.get_recommendation(user_input)
                    print(f"🎌 Bot: {recommendation}\n")
                except KeyboardInterrupt:
                    print("\n👋 Chat interrupted. Goodbye!")
                    break
                except Exception as e:
                    print(f"❌ Error: {str(e)}\n")
        except Exception as e:
            print(f"❌ Failed to start bot: {str(e)}")
        finally:
            await self.stop_server()

async def get_single_recommendation(query: str) -> str:
    bot = AnimeChatBot()
    try:
        await bot.start_server()
        return await bot.get_recommendation(query)
    finally:
        await bot.stop_server()

async def main():
    import sys
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        print(f"🎯 Query: {query}")
        result = await get_single_recommendation(query)
        print(f"🎌 Recommendation: {result}")
    else:
        bot = AnimeChatBot()
        await bot.chat()

if __name__ == "__main__":
    asyncio.run(main())
