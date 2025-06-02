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

#set_default_openai_key(os.getenv("OPENAI_API_KEY"))
openai_key = os.getenv("OPENAI_API_KEY")
linkup_key = os.getenv("LINKUP_API_KEY")
linkup_client = LinkupClient(api_key=linkup_key)



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


    variables = {
        "id" : id
    }

    url = 'https://graphql.anilist.co'

    # Make the HTTP Api request
    response = requests.post(url, json={'query': query, 'variables': variables})

    return parse_anime_response(response.json())


@function_tool
async def search_web(query : str) -> str:
  """
    Searches the web for anime recommendations or related information.

    Use this tool when the user asks for suggestions, comparisons, or trends
    that may not be available in structured datasets (like AniList), or if
    real-time popularity or reviews are needed.

    Args:
        query (str): A natural language query about anime, such as
                     "anime like Cowboy Bebop" or
                     "funny school life anime".

    Returns:
        str: A formatted string containing the top 3 web search results
             including title, link, and a short content snippet.
    """
  response = await linkup_client.async_search(
      query = query,
      depth='standard',
      output_type='searchResults'
  )
  answer = f"Search results for '{query}' on {datetime.now().strftime('%Y-%m-%d')}\n\n"
  for result in response.results[:3]:
      answer += f"{result.name}\n{result.url}\n{result.content}\n\n"
  return answer


async def run_agent_with_servers(mcp_server: MCPServerStdio) -> None:
    """
    Run the agent with the given MCP server.
    """
    # Define the agent
    anime_anilist_agent = Agent(
        name="Anime Recommender",
        model="gpt-4o-mini",
        instructions = (
        "You are an intelligent anime recommendation agent.\n"
        "Your job is to understand user preferences and use the available AniList tools to recommend the most relevant anime.\n"
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
        "- Return up to 5 anime titles that best match the user's request\n"
        "- Assign each title a score out of 10 based on relevance to the request\n"
        "- Include brief reasoning for each score (1-2 sentences max)\n"
        "- NEVER invent anime titles - only use results from AniList tools\n"
        "- Format: 'Title Name - Score/10: Brief reason'\n"
        "- Do not include extra commentary beyond the scored recommendations"
        ),
        mcp_servers=[mcp_server],
        tools=[get_tags,get_anime_search]
    )

    web_search_agent = Agent(
        name = "Web Search Agent",
        model = "gpt-4o-mini",
        instructions =(
            "You are a web search agent focused on anime recommendations. "
            "When given a user query, your job is to search the web using the `search_web` tool "
            "and return exactly 5 anime recommendations that are the closest match to the user's request. "
            "For each anime you recommend, assign a score out of 10 that reflects how well it matches "
            "the user's description, based on the content of the search results. "
            "Only return the anime title and its score. Do not include explanations, links, or additional commentary. "
            "Use the search tool only once per request and be as accurate as possible based on the search content."
        ),
        tools = [search_web]
    )



    main_agent = Agent(
        name="Anime Recommender Main Agent",
        model = "gpt-4o-mini",
        instructions = RECOMMENDED_PROMPT_PREFIX + (
            "You are an anime recommendation orchestrator. "
            "You manage two specialized agents:\n"
            "- `anime_anilist_agent` (AniList-based recommendations)\n"
            "- `web_search_agent` (web-based recommendations for highly specific or niche cases)\n\n"

            "Decision and Handoff Logic:\n"
            "- If the user's query is general or popular (e.g., 'anime like Cowboy Bebop', 'best fantasy romance anime'), use a **handoff to anime_anilist_agent**.\n"
            "- If the user's query is very specific, nuanced, or depends on real-world or trending knowledge (e.g., 'anime with frogs that run a tea shop'), use a **handoff to web_search_agent**.\n"
            "- If the query is multi-faceted or ambiguous and could benefit from both structured data and web context, use **both agents as tools** in parallel.\n"
            "- In the case of **both agents as tools** in parallel, DO NOT use both agents multiple times for the same query. Instead, use each agent once and combine their outputs.\n" 
            "- DO NOT use either agent as a tool by itself — only use tools when **both agents are needed together**.\n\n"

            "Output Requirements:\n"
            "- Return up to 5 anime titles that best match the user's request\n"
            "- Assign each title a score out of 10 based on relevance to the request\n"
            "- Include brief reasoning for each score (1–2 sentences max)\n"
            "- NEVER invent anime titles — only use results from AniList or Web Search tools\n"
            "- Format: 'Title Name – Score/10: Brief reason'\n"
            "- Do not include extra commentary beyond the scored recommendations"
        ),
        tools = [
            web_search_agent.as_tool(
                tool_name = "web_search_agent",
                tool_description = "Searches the web for anime recommendations or related information."
            ),

            anime_anilist_agent.as_tool(
                tool_name = "anime_anilist_agent",
                tool_description = "An intelligent anime recommendation agent that uses AniList tools to recommend the most relevant anime based on user preferences."
            )
        ],
        handoffs = [anime_anilist_agent , web_search_agent],
        handoff_description=(
        "Use the anime_anilist_agent for general or popular anime recommendation queries. (e.g., 'anime like Cowboy Bebop', 'best fantasy romance anime')\n"
        "Use the web_search_agent when the query is unusually specific or too niche. (e.g., 'anime with frogs that run a tea shop') "
        )
    )

    # Run the agent
    result = await Runner.run(
        starting_agent=main_agent,
        input="I need an anime that talks about slavery and stuff"
    )
    
    print("\n✅ Final Output:\n")
    print(result.final_output)

EXCLUDED_TOOLS = {
    'get_media_tags',  # Only exclude this tool
}

async def anilist_example() -> None:
    try:
        async with MCPServerStdio(
            name="Anilist Server",
            params={
                "command": "npx",
                "args": ["-y", "anilist-mcp"],
                # Optional: Add ANILIST_TOKEN if you need authenticated operations
                # "env": {
                #     "ANILIST_TOKEN": os.getenv("ANILIST_TOKEN")
                # }
            }, cache_tools_list=True
        ) as server:

            trace_id = gen_trace_id()
            print(f"View Trace: https://platform.openai.com/traces/{trace_id}")

            tools = await server.list_tools()
            print(f"Available tools: {[tool.name for tool in tools]}")
            await run_agent_with_servers(server)
    
    except Exception as e: 
        print(f"An error occurred: {e}")


async def main() -> None:
    if not shutil.which("npx"):
        print("npx is not installed. Please install Node.js and try again.")
        return
    
    await anilist_example()
    print("Done! You can now run the agent with the MCP server.")


if __name__ == "__main__":
    asyncio.run(main())