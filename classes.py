from enum import Enum
import json

import os

from datetime import datetime, timedelta, time
from tzlocal import get_localzone

from gcsa.event import Event
from gcsa.google_calendar import GoogleCalendar

google_account = "" # simply a working email which is organised by oauth
with open("config.json", "r") as f:
    google_account = json.loads(f.read())["email"]

tag = "#auto"
local_timezone = get_localzone()

class GCColour(Enum):
    TOMATO = 11
    FLAMINGO = 4
    TANGERINE = 6
    BANANA = 5
    SAGE = 2
    BASIL = 10
    # PEACOCK = None (no colour for the event is this colour)
    BLUEBERRY = 9
    LAVENDER = 1
    GRAPE = 3
    GRAPHITE = 8

def times_intersect(x1,x2,y1,y2):
    if x2 == y1 or y2 == x1:
        return False
    
    return x2 >= y1 and y2 >= x1

def contextualise(time, date):
    """
    Adds a date to a time, allowing for the time to be compared against the global timeline
    """
    return date.replace(hour=time.hour,minute=time.minute,second=time.second)


class Task:
    def __init__(self, name, desc, minutes, due):
        # time will be in minutes, just an integer
        self.length = timedelta(minutes=minutes)
        self.due = due
        self.name = name
        self.desc = desc
    
    def __repr__(self):
        return f"Task({self.name}, {self.desc})"

class Calendar:
    def __init__(self, active_time, inactive_time):
        self.tasks_by_due = []

        self.link = GoogleCalendar(google_account) # link to google

        self.log_on = active_time # this should be a datetime object of the time when you start being active
        self.log_off = inactive_time

        self.uploaded_events = [] # needs to be saved, list of event ids
        if os.path.isfile("events.json"):
            with open("events.json", "r") as f:
                self.uploaded_events = json.loads(f.read())

        self.events = self.get_events()
        print(self.events)
    
    def get_events(self):
        events = []

        for event in sorted(self.link.get_events()):
            if not (event.description is not None and event.description.endswith(tag)):
                events.append(event)
        
        return events
    
    def get_tasks(self, delete=False):
        tasks = []

        for event in self.link:
            if event.description and event.description.endswith(tag): # all the descriptions must end with this
                tasks.append(event)

                if delete is True:
                    self.link.delete_event(event) 
        
        return tasks

    def insert_task(self, task):
        inserted = False
        for i,v in enumerate(self.tasks_by_due):
            if v.due > task.due:
                self.tasks_by_due.insert(i,task)
                inserted = True
                break
        
        if inserted is False: self.tasks_by_due.append(task)

    def organise_calendar(self):
        """
        Creates a valid new calendar, organising tasks by due date and around events.
        
        To be implemented in order of priority:
        1) (Assuming all tasks are assignable easily in the order by due date) lay out all tasks by due date.
        2) Lay out all tasks by due date if tasks can be switched around and still give a valid layout. (ex: short task taking up space on day 2 when day 1 has a gap free for it)
        3) Split up tasks into smaller segments (if needed and opted in)
        4) If the layout isn't possible and you're swamped, extend log_off time by increments of 30 minutes (includes log_off time being technically before log_on time, if log_off is 2am and log_on is 7am)
        """
        # let's find the first active moment that's a multiple of 15 minutes after when this is being run

        now = datetime.now(local_timezone) 
        fifteen_minutes = timedelta(minutes=15)

        current_minute = now.minute
        if current_minute % 15 != 0:
            # i couldn't think of a better way to do this
            for i in range(15):
                current_minute -= 1
                if current_minute % 15 == 0:
                    break
        
        now = now.replace(minute=current_minute,second=0,microsecond=0)
        now += fifteen_minutes # this is now the first 15 minute starter

        now_time = now.time()

        if (now_time < self.log_on) or (now_time > self.log_off): # this assumes that if placed on the same day, log_on would be before log_off
            # we're in inactive hours, skip ahead to you logging on

            while (now_time < self.log_on) or (now_time > self.log_off):
                # continue adding 15 minutes until it is a valid time
                now += fifteen_minutes
                now_time = now.time()
        
        # now_time is now a valid time to try the place to calendar logic
        
        working_time = contextualise(now_time, now)

        task_list = [] # tuple(time: starting_time, task: task assigned to this time)

        # keep skipping forwards fifteen minutes until a slot is found which doesn't collide with log_off time and any scheduled events

        for i in range(len(self.tasks_by_due)):
            task = self.tasks_by_due.pop(0)

            while True: # logic to break is too complicated to be handled in a statement
                valid = True

                end = working_time + task.length

                # consider a number line and the intersection of 2 1d segments
                # additionally, if the log_on or log_off lies within working_time and end, it is also invalid (this logic is harder though)

                # if the starting time of the event we are on is after end, then we can break the loop (iterating through events is hard when it goes through the next year's worth)

                for event in self.events:
                    print(event, event.start, event.end, working_time, "event loop")
                    # check for collisions as described above
                    if times_intersect(working_time, end, event.start, event.end):
                        valid = False
                        break # we don't need to check any more

                    if event.start > end:
                        # all further events are after this
                        break
                
                # log_on log_off collision cases:
                # log_on start log_off end
                # log_on start log_off log_on .... end

                # place the log_off time on the date at which the task will be done
                day_specific_log_off = contextualise(self.log_off, working_time)

                if end > day_specific_log_off:
                    # this is an impossible configuration, it isn't valid
                    valid = False
                
                # currently the assumption is that all tasks are able to be fit in order before the due date, so task.due isn't referenced yet
                # TODO: task.due

                if valid is True:
                    break

                working_time += fifteen_minutes

            task_list.append((working_time, task))
            working_time += task.length
        
        return task_list

    def upload_task_list(self,task_list):
        for time,task in task_list:
            event = Event(start=time,end=time+task.length,description=task.desc+tag,color_id=GCColour.TOMATO.value,summary=task.name)

            event = self.link.add_event(event)

            self.uploaded_events.append(event.event_id)
        
        with open("events.json", "w") as f:
            f.write(json.dumps(self.uploaded_events))

    def get_uploaded_tasks(self, filterCompleted=False):
        tasks = []

        for event_id in self.uploaded_events:
            task = self.link.get_event(event_id)
            if filterCompleted and task.color_id in [GCColour.BASIL.value, GCColour.SAGE.value]:
                # it's completed (marked as green), skip it
                continue
            
            tasks.append(task)

        return tasks

                
# cheeky little test case

c = Calendar(time(hour=7), time(hour=18))

t1 = Task("not important", "do something", 60,0)
t2 = Task("pop method", "pop 1 singular method", 30,0)
t3 = Task("poop", "take a poo", 120,0)

c.insert_task(t1)
c.insert_task(t2)
c.insert_task(t3)

tl = c.organise_calendar()

c.upload_task_list(tl)