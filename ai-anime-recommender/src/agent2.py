from agents.mcp import MCPServerStdio
import asyncio
import os 
import shutil
import sys
from agents import Agent, Runner, function_tool, set_default_openai_key, gen_trace_id
from dotenv import load_dotenv
import json
import requests

with open('tags.json', 'r') as file:
    tags = json.load(file)

all_tags = [
    tag["name"] for tag in tags["data"]["MediaTagCollection"] if not tag.get("isAdult" , False)
]

# Parsing function for get_anime_search tool 
def parse_anime_response(raw_json):
    media = raw_json.get("data", {}).get("Media", {})

    # Title (fallback to romaji if english missing)
    title_data = media.get("title", {})
    title = title_data.get("english") or title_data.get("romaji", "Unknown Title")

    # Description cleanup
    raw_desc = media.get("description", "")
    description = raw_desc.replace("<br><br>", "\n").split("\n")[0].strip()

    # Genres and Tags
    genres = media.get("genres", [])
    tags = [tag["name"] for tag in media.get("tags", [])][:5]

    # Start date formatting
    start = media.get("startDate", {})
    start_date = f"{start.get('year', '??')}-{str(start.get('month', '??')).zfill(2)}-{str(start.get('day', '??')).zfill(2)}"

    # Other metadata
    country = media.get("countryOfOrigin", "Unknown")
    duration = media.get("duration", 0)
    episodes = media.get("episodes", 0)

    # Recommendations
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

load_dotenv()
openai_key = os.getenv("OPENAI_API_KEY")

@function_tool
async def get_tags() -> list:
    """
    Returns a list of all available tags on AniList.
    """
    return all_tags

@function_tool
async def get_anime_search(id: int) -> dict:
    query = """
    query ($id: Int) {
    Media(id: $id, type: ANIME) {
        title {
        romaji
        english
        }
        startDate {
        day
        month
        year
        }
        countryOfOrigin
        genres
        duration
        episodes
        tags {
        name
        }
        description(asHtml: false)

        recommendations(perPage: 10, sort: RATING_DESC) {
        edges {
            node {
            rating
            mediaRecommendation {
                title {
                english
                }
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
    return parse_anime_response(response.json())

class AnimeChatBot:
    def __init__(self, mcp_server):
        self.mcp_server = mcp_server
        self.agent = Agent(
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
                "- When giving recommendations, include up to 5 anime titles that best match the user's request\n"
                "- Assign each title a score out of 10 based on relevance to the request\n"
                "- Include brief reasoning for each score (1-2 sentences max)\n"
                "- NEVER invent anime titles - only use results from AniList tools\n"
                "- Format recommendations as: 'Title Name - Score/10: Brief reason'\n"
                "- Be conversational and friendly in your responses\n"
                "- Ask follow-up questions when appropriate to better understand preferences"
            ),
            mcp_servers=[mcp_server],
            tools=[get_tags, get_anime_search]
        )
    
    async def chat(self, user_input: str) -> str:
        """Send a message to the anime bot and get a response"""
        try:
            result = await Runner.run(
                starting_agent=self.agent,
                input=user_input
            )
            return result.final_output
        except Exception as e:
            return f"Sorry, I encountered an error: {str(e)}"

async def run_chat_interface(mcp_server):
    """Run the interactive chat interface"""
    bot = AnimeChatBot(mcp_server)
    
    print("🎌 Anime Recommendation Chat Bot Started!")
    print("Type 'quit', 'exit', or 'bye' to end the conversation.")
    print("Type 'help' for usage examples.")
    print("-" * 50)
    
    while True:
        try:
            # Get user input
            user_input = input("\n💬 You: ").strip()
            
            # Check for exit commands
            if user_input.lower() in ['quit', 'exit', 'bye', 'q']:
                print("\n👋 Thanks for using the Anime Recommendation Bot! Goodbye!")
                break
            
            # Handle empty input
            if not user_input:
                print("Please enter a message or type 'quit' to exit.")
                continue
            
            # Handle help command
            if user_input.lower() == 'help':
                print("\n📚 Usage Examples:")
                print("• 'I want funny high school anime with good ratings'")
                print("• 'Recommend me something similar to Attack on Titan'")
                print("• 'What anime has the character Naruto?'")
                print("• 'Show me romance anime from 2020'")
                print("• 'I like action and fantasy genres'")
                continue
            
            # Get bot response
            print("\n🤖 Bot: Thinking...")
            response = await bot.chat(user_input)
            print(f"🤖 Bot: {response}")
            
        except KeyboardInterrupt:
            print("\n\n👋 Chat interrupted. Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {str(e)}")

async def initialize_mcp_server():
    """Initialize and return the MCP server"""
    try:
        server = MCPServerStdio(
            name="Anilist Server",
            params={
                "command": "npx",
                "args": ["-y", "anilist-mcp"],
                # Optional: Add ANILIST_TOKEN if you need authenticated operations
                # "env": {
                #     "ANILIST_TOKEN": os.getenv("ANILIST_TOKEN")
                # }
            }, cache_tools_list=True
        )
        
        # Initialize the server
        await server.__aenter__()
        
        # List available tools for debugging
        tools = await server.list_tools()
        print(f"✅ Connected to AniList MCP Server")
        print(f"📋 Available tools: {[tool.name for tool in tools]}")
        
        return server
        
    except Exception as e:
        print(f"❌ Failed to initialize MCP server: {e}")
        raise

async def main():
    """Main function to run the chat bot"""
    if not shutil.which("npx"):
        print("❌ npx is not installed. Please install Node.js and try again.")
        return
    
    if not openai_key:
        print("❌ OPENAI_API_KEY not found in environment variables.")
        print("Please add your OpenAI API key to your .env file.")
        return
    
    server = None
    try:
        # Initialize MCP server
        server = await initialize_mcp_server()
        
        # Generate trace ID for debugging
        trace_id = gen_trace_id()
        print(f"🔍 View Trace: https://platform.openai.com/traces/{trace_id}")
        
        # Run the chat interface
        await run_chat_interface(server)
        
    except Exception as e:
        print(f"❌ An error occurred: {e}")
    finally:
        # Clean up the server connection
        if server:
            try:
                await server.__aexit__(None, None, None)
                print("🔌 Disconnected from MCP server")
            except:
                pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Program terminated by user. Goodbye!")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)