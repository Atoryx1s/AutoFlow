import requests
import logging
from config import OWM_API_KEY

logger = logging.getLogger(__name__)

def get_weather(city="Kosice"):
    try:
        url = f"https://openweathermap.org{city}&appid={OWM_API_KEY}&units=metric&lang=sk"
        response = requests.get(url, timeout=10)
        data = response.json()
        if response.status_code == 200:
            temp = data["main"]["temp"]
            desc = data["weather"][0]["description"].capitalize()
            return f"{desc}, {round(temp)}°C"
        return "Neznámé"
    except Exception as e:
        logger.error(f"Error fetching weather: {e}")
        return "Neznámé"
