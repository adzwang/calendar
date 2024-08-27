from classes import Task, Calendar

import json

from datetime import time, datetime, timedelta

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

