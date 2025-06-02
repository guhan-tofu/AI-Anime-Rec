from flask import Flask, jsonify, request
from flask_cors import CORS
import asyncio
from agent import AnimeChatBot 
from parse import parse_titles_and_fetch_details




app = Flask(__name__)
cors = CORS(app, origins="*")


@app.route('/api/users', methods=['GET'])
def users():
    return jsonify(
        {
            "users": [
                "jeff",
                "john",
                "jimmy",
            ]
        }
    )

bot = AnimeChatBot() # Global instance of the bot

@app.route('/recommend', methods=['POST'])
def recommend():
    data = request.get_json()
    user_input = data.get("query","")

    if not user_input:
        return jsonify({"error": "No query provided"}), 400

    async def run_bot():

        try:
            await bot.start_server()
            result = await bot.get_recommendation(user_input)
            return result
        finally:
            await bot.stop_server()

    result = asyncio.run(run_bot())
    anime_info = parse_titles_and_fetch_details(result)
    return jsonify({"recommendation": anime_info})



if __name__ == '__main__':
    app.run(debug=True, port=8080)