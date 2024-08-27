from classes import Task, Calendar

import json

from datetime import time, datetime, timedelta
from threading import Thread
from time import sleep

def parse_time(string):
    index = string.find(":")

    hour = int(string[:index])
    minute = int(string[index+1:])

    return time(hour=hour,minute=minute)

with open("config.json", "r") as f:
    data = json.loads(f.read())
    log_on = parse_time(data["log_on"])
    log_off = parse_time(data["log_off"])

calendar = Calendar(log_on, log_off)

# we have our calendar, deal with a refresh loop

def refresh():
    while True:
        sleep(60)
        calendar.reload_tasks() # refresh the calendar every minute, checking for new events which would interrupt the current tasks


loop = Thread(target=refresh)
loop.run()