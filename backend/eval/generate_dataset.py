import csv
import json
import os
import random

import yaml
from google import genai
from pydantic import BaseModel, Field


class Filter(BaseModel):
    operating_systems: list[str] | None = Field(
        default=None, description="e.g. windows, mac, linux"
    )
    categories: list[str] | None = Field(default=None)
    genres: list[str] | None = Field(default=None)
    tags: list[str] | None = Field(default=None)
    supported_languages: list[str] | None = Field(default=None)
    minimum_rating_percent: int | None = Field(default=None)
    maximum_price: float | None = Field(default=None)


class TestCase(BaseModel):
    id: str = Field(description="Unique short id, e.g. en_strategy_mac")
    query: str = Field(
        description=(
            "Natural language query in some language "
            "(mix languages like English, Spanish, German, Ukrainian, Russian, Chinese)"
        )
    )
    relevant_app_ids: list[int]
    filters: Filter


def main() -> None:
    csv_path = "data/steam_games.csv"
    games = []

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                pos = int(row["Positive"])
                if pos > 100000:  # Popular games
                    games.append(row)
            except ValueError:
                pass

    print(f"Found {len(games)} popular games.")

    # Select 50 random games
    random.seed(42)
    selected_games = random.sample(games, 50) if len(games) >= 50 else games

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        try:
            with open(".env") as env_file:
                for line in env_file:
                    if line.startswith("GEMINI_API_KEY="):
                        api_key = line.strip().split("=", 1)[1]
        except FileNotFoundError:
            pass
    client = genai.Client(api_key=api_key)

    prompt = """
    You are an expert at creating search evaluation datasets. 
    I will provide a Steam game's metadata. 
    You need to create a realistic search query that a user might type
    to find exactly this game (or games like it).
    The query should be natural language
    (e.g., "co-op space survival game for linux" or "juego de granja relajante").
    Vary the languages of the queries (English, Spanish, German, French, Ukrainian, etc.).
    Extract the canonical filters that apply to this query.
    
    Game Metadata:
    Name: {name}
    AppID: {appid}
    Genres: {genres}
    Tags: {tags}
    Categories: {categories}
    Platforms (Win/Mac/Linux): {win}/{mac}/{linux}
    Price: {price}
    Languages: {langs}
    
    Generate exactly one test case.
    """

    test_cases = []
    for i, game in enumerate(selected_games):
        print(
            f"Generating for {i + 1}/50: {game['Name'].encode('ascii', 'ignore').decode('ascii')}"
        )

        langs = ["English", "Spanish", "German", "French", "Ukrainian", "Russian", "Chinese"]
        chosen_lang = random.choice(langs)

        game_prompt = prompt.format(
            name=game["Name"],
            appid=game["AppID"],
            genres=game["Genres"],
            tags=game["Tags"],
            categories=game["Categories"],
            win=game["Windows"],
            mac=game["Mac"],
            linux=game["Linux"],
            price=game["Price"],
            langs=game["Supported languages"],
        )
        game_prompt += f"\n\nPlease write the query primarily in {chosen_lang}."

        try:
            response = client.models.generate_content(
                model="gemini-3.5-flash",
                contents=game_prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": TestCase,
                },
            )
            data = json.loads(response.text)

            # Ensure relevant_app_ids contains the target app id
            data["relevant_app_ids"] = [int(game["AppID"])]

            # Clean up empty filters
            filters = {k: v for k, v in data["filters"].items() if v}
            data["filters"] = filters

            test_cases.append(data)
        except Exception as e:
            print(f"Error generating for {game['Name']}: {e}")

    # Write to dataset.yaml
    output = {"cases": test_cases}
    with open("dataset_new.yaml", "w", encoding="utf-8") as f:
        yaml.dump(output, f, allow_unicode=True, sort_keys=False)

    print("Done generating dataset_new.yaml")


if __name__ == "__main__":
    main()
