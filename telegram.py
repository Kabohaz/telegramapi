import json
import requests
import time
import urllib
import logging
import signal
import sys

TOKEN = "secrettoken"
OWM_KEY = "secretkey"
POLLING_TIMEOUT = None

# Lambda functions to parse updates from Telegram
def getText(update):            return update["message"]["text"]
def getLocation(update):        return update["message"]["location"]
def getChatId(update):          return update["message"]["chat"]["id"]
def getUpId(update):            return int(update["update_id"])
def getResult(updates):         return updates["result"]

# Lambda functions to parse weather responses
def getDesc(w):                 return w["weather"][0]["description"]
def getTemp(w):                 return w["main"]["temp"]
def getCity(w):                 return w["name"]
logger = logging.getLogger("weather-telegram")
logger.setLevel(logging.DEBUG)

# Cities for weather requests
cities = ["London", "Paris"]

def sigHandler(signal, frame):
    logger.info("SIGINT received. Exiting... Bye bye")
    sys.exit(0)

# Configure file and console logging
def configLogging():
    # Create file logger and set level to DEBUG
    # Mode = write -> clear existing log file
    handler = logging.FileHandler("run.log", mode="w")
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Create console handler and set level to INFO
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter("[%(levelname)s] - %(message)s")
    ch.setFormatter(formatter)
    logger.addHandler(ch)

def parseConfig():
    global URL, URL_OWM, POLLING_TIMEOUT
    URL = "https://api.telegram.org/bot{}/".format(TOKEN)
    URL_OWM = "http://api.openweathermap.org/data/2.5/weather?appid={}&lang=en&units=metric".format(OWM_KEY)
    POLLING_TIMEOUT

# Make a request to Telegram bot and get JSON response
def makeRequest(url):
    logger.debug("URL: %s" % url)
    r = requests.get(url)
    resp = json.loads(r.content.decode("utf8"))
    return resp

# Return all the updates with ID > offset
# (Updates list is kept by Telegram for 24h)
def getUpdates(offset=None):
    url = URL + "getUpdates?timeout=%s" % POLLING_TIMEOUT
    logger.info("Getting updates") 
    if offset:
        url += "&offset={}".format(offset)
    js = makeRequest(url)
    return js

# Build a one-time keyboard for on-screen options
def buildKeyboard(items):
    keyboard = [[{"text":item}] for item in items]
    replyKeyboard = {"keyboard":keyboard, "one_time_keyboard": True}
    logger.debug(replyKeyboard)
    return json.dumps(replyKeyboard)

def buildCitiesKeyboard():
    keyboard = [[{"text": c}] for c in cities]
    keyboard.append([{"text": "Share location", "request_location": True}])
    replyKeyboard = {"keyboard": keyboard, "one_time_keyboard": True}
    logger.debug(replyKeyboard)
    return json.dumps(replyKeyboard)

# Query OWM for the weather for place or coords
def getWeather(place):
    if isinstance(place, dict):     # coordinates provided
        lat, lon = place["latitude"], place["longitude"]
        url = URL_OWM + "&lat=%f&lon=%f&cnt=1" % (lat, lon)
        logger.info("Requesting weather: " + url)
        js = makeRequest(url)
        logger.debug(js)
        return u"%s \N{DEGREE SIGN}C, %s in %s" % (getTemp(js), getDesc(js), getCity(js))
    else:                           # place name provided 
        # make req
        url = URL_OWM + "&q={}".format(place)
        logger.info("Requesting weather: " + url)
        js = makeRequest(url)
        logger.debug(js)
        return u"%s \N{DEGREE SIGN}C, %s in %s" % (getTemp(js), getDesc(js), getCity(js))

# Send URL-encoded message to chat id
def sendMessage(text, chatId, interface=None):
    text = text.encode('utf-8', 'strict')                                                       
    text = urllib.parse.quote_plus(text)
    url = URL + "sendMessage?text={}&chat_id={}&parse_mode=Markdown".format(text, chatId)
    if interface:
        url += "&reply_markup={}".format(interface)
    requests.get(url)

# Get the ID of the last available update
def getLastUpdateId(updates):
    ids = []
    for update in getResult(updates):
        ids.append(getUpId(update))
    return max(ids)

# Keep track of conversation states: 'weatherReq'
chats = {}

# Echo all messages back
def handleUpdates(updates):
    for update in getResult(updates):
        chatId = getChatId(update)
        try:
            text = getText(update)
        except Exception as e:
            logger.error("No text field in update. Try to get location")
            loc = getLocation(update)
            # Was weather previously requested?
            if (chatId in chats) and (chats[chatId] == "weatherReq"):
                logger.info("Weather requested for %s in chat id %d" % (str(loc), chatId))
                # Send weather to chat id and clear state
                sendMessage(getWeather(loc), chatId)
                del chats[chatId]
            continue

        if text == "/weather":
            keyboard = buildCitiesKeyboard()
            chats[chatId] = "weatherReq"
            sendMessage("Choose a city", chatId, keyboard)
        elif text == "/start":
            sendMessage("Type weather to open the menu", chatId)
        elif text.startswith("/"):
            logger.warning("Error, use correct commands %s" % text)    
            continue
        elif (text in cities) and (chatId in chats) and (chats[chatId] == "weatherReq"):
            logger.info("Weather for %s" % text)
            # Send weather to chat id and clear state
            sendMessage(getWeather(text), chatId)
            del chats[chatId]
        else:
            keyboard = buildKeyboard(["/weather"])
            sendMessage("I can now tell you about the weather", chatId, keyboard)

def main():
    # Set up file and console loggers
    configLogging()

    # Get tokens and keys
    parseConfig()
 
    # Intercept Ctrl-C SIGINT 
    signal.signal(signal.SIGINT, sigHandler) 
 
    # Main loop
    last_update_id = None
    while True:
        updates = getUpdates(last_update_id)
        if len(getResult(updates)) > 0:
            last_update_id = getLastUpdateId(updates) + 1
            handleUpdates(updates)
        time.sleep(0.5)

if __name__ == "__main__":
    main()
