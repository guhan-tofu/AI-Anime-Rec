# filepath: /ai-anime-recommender/ai-anime-recommender/src/main.py
import asyncio
from agent import recommend_anime
async def run():
    prompt = "I need an anime like Cowboy Bebop"
    result = await recommend_anime(prompt)
    print(result)

if __name__ == "__main__":
    asyncio.run(run())