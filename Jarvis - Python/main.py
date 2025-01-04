import speech_recognition as sr     #to simplify usage of speechrecognition, use 'as'
import webbrowser   #module to open web browser using python
import pyttsx3      # to convert text to speech
import musicLib #user defined music library
import requests
from openai import OpenAI
from gtts import gTTS
import pygame
import time
import os
import openmeteo_requests
import requests_cache
import pandas as pd
from retry_requests import retry
from datetime import datetime, timedelta

recognizer = sr.Recognizer()    #recognizer object to recognize speech
engine = pyttsx3.init()           #text to speech object to convert text to speech
apiKey = "x"

#uses regular microsoft text to speech
def speakOld(text):
    engine.say(text)
    engine.runAndWait()

def speak(text):
    tts = gTTS(text)
    tts.save("temp.mp3")
    # Initialize Pygame
    pygame.mixer.init()

    # Load the MP3 file
    pygame.mixer.music.load("temp.mp3")

    # Play the MP3 file
    pygame.mixer.music.play()

    # Keep the program running while the music is playing
    # You can adjust the sleep time or use a loop to keep the program alive
    while pygame.mixer.music.get_busy():
        pygame.time.Clock().tick(10)

    pygame.mixer.music.unload()
    os.remove("temp.mp3")


#this requires paid version of open ai's api key
def aiProcess(command):
    client = OpenAI()

    completion = client.chat.completions.create(
        model="gpt-3.5-turbo-mini",
        messages=[
            {"role": "system", "content": "You are a virtual assistant named jarvis similar to alexa and siri"},
            {
                "role": "user",
                "content": "Explain concept of api"
            }
        ]
    )

    print(completion.choices[0].message)

def weather():
    # Setup the Open-Meteo API client with cache and retry on error
    cache_session = requests_cache.CachedSession('.cache', expire_after = 3600)
    retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
    openmeteo = openmeteo_requests.Client(session = retry_session)

    # Make sure all required weather variables are listed here
    # The order of variables in hourly or daily is important to assign them correctly below
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": 18.31,
        "longitude": 73.51,
        "current": "wind_speed_10m",
        "hourly": ["temperature_2m", "rain"],
        "daily": ["temperature_2m_max", "temperature_2m_min", "sunrise", "sunset"],
        "forecast_days": 1
    }
    responses = openmeteo.weather_api(url, params=params)

    # Process first location. Add a for-loop for multiple locations or weather models
    response = responses[0]

        # Current values. The order of variables needs to be the same as requested.
    current = response.Current()
    current_wind_speed_10m = current.Variables(0).Value()

    speak(f"Current time is {current.Time()}")
    speak(f"Current wind speed is {current_wind_speed_10m}")

    # Process hourly data. The order of variables needs to be the same as requested.
    hourly = response.Hourly()
    hourly_temperature_2m = hourly.Variables(0).ValuesAsNumpy()
    hourly_rain = hourly.Variables(1).ValuesAsNumpy()

    hourly_data = {"date": pd.date_range(
        start = pd.to_datetime(hourly.Time(), unit = "s", utc = True),
        end = pd.to_datetime(hourly.TimeEnd(), unit = "s", utc = True),
        freq = pd.Timedelta(seconds = hourly.Interval()),
        inclusive = "left"
    )}
    hourly_data["temperature_2m"] = hourly_temperature_2m
    hourly_data["rain"] = hourly_rain

    hourly_dataframe = pd.DataFrame(data = hourly_data)
    print(hourly_dataframe)
    speak(hourly_dataframe)

    # Process daily data. The order of variables needs to be the same as requested.
    daily = response.Daily()
    daily_temperature_2m_max = daily.Variables(0).ValuesAsNumpy()
    daily_temperature_2m_min = daily.Variables(1).ValuesAsNumpy()
    daily_sunrise = daily.Variables(2).ValuesAsNumpy()
    daily_sunset = daily.Variables(3).ValuesAsNumpy()

    daily_data = {"date": pd.date_range(
        start = pd.to_datetime(daily.Time(), unit = "s", utc = True),
        end = pd.to_datetime(daily.TimeEnd(), unit = "s", utc = True),
        freq = pd.Timedelta(seconds = daily.Interval()),
        inclusive = "left"
    )}
    daily_data["temperature_2m_max"] = daily_temperature_2m_max
    daily_data["temperature_2m_min"] = daily_temperature_2m_min
    daily_data["sunrise"] = daily_sunrise
    daily_data["sunset"] = daily_sunset

    daily_dataframe = pd.DataFrame(data = daily_data)
    print(daily_dataframe)
    speak(daily_dataframe)

def processCommand(c):  #function for processing the command
    if "open google" in c.lower():
        webbrowser.open("https://google.com")
    elif "open youtube" in c.lower():
        webbrowser.open("https://youtube.com")
    elif "open netflix" in c.lower():
        webbrowser.open("https://netflix.com")
    elif "open gmail" in c.lower():
        webbrowser.open("https://gmail.com")
    elif "open linkedin" in c.lower():
        webbrowser.open("https://linkedin.com")
    elif "open spotify" in c.lower():
        webbrowser.open("https://open.spotify.com/search/stan?flow_ctx=c8ffbd14-9850-4669-9015-0971400394c7%3A1736036348#login")
    #for playing songs
    elif c.lower().startswith("play"):
        song = c.lower().split(" ")[1]
        link = musicLib.music[song]
        webbrowser.open(link)
    elif "headlines" in c.lower():
        r = requests.get(f"https://newsapi.org/v2/top-headlines?country=in&apiKey=2a4270b20b1d40aabc7267f195313411")    #returns a json and stores in r
        if r.status_code == 200:
            data = r.json()     #parse json response
            articles = data.get("articles",[])  #extracting the articles
            for article in articles:
                speak(article.get("title"))
    elif "weather" in c.lower():
        weather()
    elif "time" in c.lower():
        speak("The current time is " + str(datetime.datetime.now().strftime("%H:%M:%S")))
    elif "date" in c.lower():
        speak("The current date is " + str(datetime.datetime.now().strftime("%d/%m")))
    else:
        speak("Sorry I didn't understand that!")

if __name__ == "__main__":
    speak("Initializing Jarvis...")
    while True:
        #Listen for the wake word 'Jarvis'

        # obtain audio from the microphone
        r = sr.Recognizer()
        print("recognizing...")

        # recognize speech using google
        try:
            with sr.Microphone() as source:
                print("Listening...")
                audio = r.listen(source, timeout=2, phrase_time_limit=1)
            command = r.recognize_google(audio)
            if "jarvis" in command.lower():
                speak("How may I help you sir?")
                #listen for the command
                with sr.Microphone() as source:
                    print("Jarvis Active...")
                    audio = r.listen(source)
                    command = r.recognize_google(audio)
                    print(command)
                    processCommand(command)

        except Exception as e:
            print("Error: {0}".format(e))
