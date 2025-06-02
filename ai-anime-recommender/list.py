import json

with open('tags.json', 'r') as file:
    tags = json.load(file)


all_tags = [
    tag["name"] for tag in tags["data"]["MediaTagCollection"] if not tag.get("isAdult" , False)
]

print(all_tags)