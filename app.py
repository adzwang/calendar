from flask import Flask
from flask import request

import hashlib
import json

from datetime import time, datetime, timedelta
from threading import Thread, Event
from time import sleep

from classes import Task, Calendar

from tzlocal import get_localzone

closed = Event()

def read_config():
    with open("config.json", "r") as f:
        return json.loads(f.read())

def parse_time(string):
    index = string.find(":")

    hour = int(string[:index])
    minute = int(string[index+1:])

    return time(hour=hour,minute=minute)

data = read_config()
log_on = parse_time(data["log_on"])
log_off = parse_time(data["log_off"])

calendar = Calendar(log_on, log_off)
calendar.start()

refresh_rate = 5

def refresh():
    while True:
        if closed.is_set():
            break
        sleep(refresh_rate)
        calendar.reload_tasks() # refresh the calendar every minute, checking for new events which would interrupt the current tasks

app = Flask("Calendar")

@app.route("/")
def hello_world():
    return "<p>Hello, world!</p>"

@app.route("/upload",methods=["POST"])
def receive_event():
    html_args = request.form

    name = html_args["name"]
    desc = html_args["desc"]
    required_time = int(html_args["time"])
    due = html_args["due"]
    password = html_args["password"]

    # convert the due to a datetime object
    due = datetime.fromisoformat(due).replace(tzinfo=get_localzone())

    config = read_config()

    hash_obj = hashlib.sha512()
    hash_obj.update(password.encode("utf-8"))
    hash_obj.update(config["salt"].encode("utf-8"))

    if hash_obj.hexdigest() == config["password_hash"]:
        # now we can create the task
        calendar.insert_task(Task(name, desc=desc, minutes=required_time, due=due))
        return "<p>Inserted the task</p>", 200
    else:
        return "<p>Unauthorized request</p>", 403

@app.route("/tasks")
def serve_page():
    with open("./input.html") as f:
        return f.read()

calendar_loop = Thread(target=refresh)
calendar_loop.start()

import sys
import signal

def handler(signal, frame):
    closed.set()
    sys.exit(0)
signal.signal(signal.SIGINT, handler)
