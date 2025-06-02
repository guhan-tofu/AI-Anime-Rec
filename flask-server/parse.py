import re
import requests
import json



def parse_titles_and_fetch_details(text):
    print(text)
    titles = re.findall(r"\*\*(.*?)\*\*", text)
    anime_doc = {}

    for title in titles:
        query = """
        query ($search: String) {
            Media(search: $search, type: ANIME) {
                id
                coverImage {
                    large
                }
                description(asHtml: false)
            }
        }
        """
        variables = {"search": title}
        url = "https://graphql.anilist.co"
        response = requests.post(url, json={"query": query, "variables": variables})
        
        if response.status_code == 200:
            data = response.json()
            media = data.get("data", {}).get("Media", {})
            if media:
                anime_doc[title] = {
                    "id": media.get("id"),
                    "image": media.get("coverImage", {}).get("large", "No image available"),
                    "description": media.get("description", "No description available")
                }
        else:
            anime_doc[title] = {
                "error": f"Error fetching data: {response.status_code}"
            }
    
    print(anime_doc)  # Debugging output
    return anime_doc