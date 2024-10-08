from enum import Enum
import json

import requests

from copy import copy # already shallowcopy

from google.oauth2 import service_account

import os

from datetime import datetime, timedelta, time
from tzlocal import get_localzone

from gcsa.event import Event
from gcsa.google_calendar import GoogleCalendar
from gcsa.acl import AccessControlRule, ACLRole, ACLScopeType

# TODO: organise imports

config = None
write_calendar = "" # simply a working email which is organised by oauth
read_calendars = []

with open("config.json", "r") as f:
    config = json.loads(f.read())
    write_calendar = config["write_calendar"]
    read_calendars = config["read_calendars"]

tag = "#auto"
local_timezone = get_localzone()

default_task_length = 30 # for me, when i think of something i might want to do it's research that thing and 30 minutes should be fine
notify_before_warning = 5 # 5 minutes before, remind you to change the colour

# rewrite _get_default_credentials_path to allow for the import of service account credentials while not tampering with the library

def get_service_account_file():
    home_dir = os.path.expanduser("~")
    credential_dir = os.path.join(home_dir, ".credentials")
    
    if not os.path.exists(credential_dir):
        raise FileNotFoundError(f'Default credentials directory "{credential_dir}" does not exist.')
    
    credential_path = os.path.join(credential_dir, config["service_account_file_name"])

    return credential_path

def load_service_account_credentials():
    SERVICE_ACCOUNT_FILE = get_service_account_file()

    SCOPES = ["https://www.googleapis.com/auth/calendar"]
    token = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)

    return token

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

class NotifyRun:
    def __init__(self,url):
        self.url = url
    
    def send(self,content):
        r=requests.post(url=self.url,data=content)

class Task:
    def __init__(self, name, desc="", minutes=60, due=None):
        # time will be in minutes, just an integer
        self.length = timedelta(minutes=minutes)
        self.due = due # this is an optional parameter, if it doesn't exist then there is no time limit for this task
        self.name = name
        self.desc = desc

# TODO: TASK TO DO AFTER A CERTAIN DATE
    
    def __repr__(self):
        return f"Task({self.name}, {self.desc})"
    
    def obj(self):
        d = {
            "name": self.name,
            "desc": self.desc
        }

        mins = self.length.total_seconds() / 60
        d["length"] = round(mins)

        if self.due is not None:
            d["due"] = self.due.isoformat()
        
        return d
    
    def json(self):
        return json.dumps(self.obj())
    
    @classmethod
    def from_json(self, js):
        d = json.loads(js)
        due = d.get("due")
        if due is not None:
            due = datetime.fromisoformat(due)
        return self(d["name"], d["desc"], d["length"], due)

    @classmethod
    def from_obj(self, d):
        due = d.get("due")
        if due is not None:
            due = datetime.fromisoformat(due)
        return self(d["name"], d["desc"], d["length"], due)
        

    def __eq__(self,other):
        if isinstance(other, Task):
            return self.name == other.name and self.desc == other.desc and self.length == other.length # and self.due == other.due

        return False

class Calendar:
    def __init__(self, active_time, inactive_time, refresh_rate=5, notify_run_client=None):
        self.tasks_by_due = [] # every minute all of these are rechecked and uploaded
        self.tasks_pending = [] # in between the minute checks, if tasks are added in between they are placed on pending until the next refresh session

        # the idea of the tasks_pending is so that if the program crashes in between uploads while tasks are trying to be uploaded, they will be saved as not_uploaded
        # every time tasks_pending is added to, a save should be triggered so that next time the program is ran, it will know to refresh

        self.link = GoogleCalendar(write_calendar, credentials=load_service_account_credentials()) # link to google

        self.calendars = []

        for calendar in read_calendars:
            self.calendars.append(GoogleCalendar(calendar, credentials=load_service_account_credentials())) # a bunch of calendars which will be read from for events

        self.log_on = active_time # this should be a datetime object of the time when you start being active
        self.log_off = inactive_time

        self.refresh_rate = refresh_rate # just needed for the notification system
        self.notify = notify_run_client

        if self.notify is None:
            self.notify = NotifyRun(config["notify_run_url"])

        self.uploaded_events = [] # needs to be saved, list of Tuple(event_id, event)
        if os.path.isfile("events.json"):
            with open("events.json", "r") as f:
                obj = json.loads(f.read())

                for key,value in obj.items():
                    if key == "not_uploaded":
                        for item in value: # value is here a list[task]
                            task = Task.from_obj(item)
                            self.tasks_pending.append(task)
                    else:
                        task = Task.from_obj(value)
                        self.tasks_by_due.append(task)

                        self.uploaded_events.append((key,task))

        self.events = self.get_events()
    
    def check_access_token():
        pass
    
    def start(self):
        self.reload_tasks()
    
    def save_events(self):
        # { event_id: event, ... , not_uploaded: [event, ...]}
        obj = {}

        # merge tasks_by_due and tasks_pending
        
        obj["not_uploaded"] = [x.obj() for x in self.tasks_pending]

        for i,task in self.uploaded_events:
            obj[i] = task.obj()
        
        # now save

        with open("events.json", "w") as f:
            f.write(json.dumps(obj))
    
    def get_events(self):
        """
        DOES NOT MODIFY self.tasks_by_due
        
        Get all upcoming events from Google Calendar which are not tasks managed by this app.
        """
        events = []

        for link in self.calendars:
            for event in sorted(link.get_events()):
                if not (event.description is not None and event.description.endswith(tag)):
                    events.append(event)
            
        print(len(events))
        
        return events

    def update_events(self):
        self.events = self.get_events()
    
    def get_tasks(self, delete=False):
        """
        DOES NOT MODIFY self.tasks_by_due
        
        Get all upcoming tasks from Google calendar which are managed by this app.
        TODO: deprecate this and use events.json to get events managed by this app.
        """
        tasks = []

        for event in self.link:
            if event.description and event.description.endswith(tag): # all the descriptions must end with this
                tasks.append(event)

                if delete is True:
                    self.link.delete_event(event)
        
        return tasks

    def insert_task(self, task):
        """
        MODIFIES self.tasks_by_due

        Inserts a Task object into the to-do list.
        """
        if task.due is None:
            self.tasks_by_due.append(task)
            return
        
        inserted = False
        for i,v in enumerate(self.tasks_by_due):
            if v.due is None:
                inserted = i
                break

            if v.due > task.due:
                self.tasks_by_due.insert(i,task)
                inserted = True
                break
        
        if inserted is not True:
            self.tasks_by_due.insert(inserted,task) # the index in which the tasks start to have no due date
    
    def merge_pending(self):
        for _ in self.tasks_pending:
            self.insert_task(self.tasks_pending.pop())

    def upload_task_list(self,task_list):
        """
        Takes a List[Tuple[datetime, Task]] and uploads all tasks as events onto Google Calendar.
        """
        for time,task in task_list:
            event = Event(start=time,end=time+task.length,description=task.desc+tag,color_id=GCColour.TOMATO.value,summary=task.name)

            event = self.link.add_event(event)

            self.uploaded_events.append((event.event_id, task))
        
        self.save_events()
    
    def check_event_updates(self):
        """
        Goes through all of the tasks uploaded, and checks for modifications. If modified, update the clientside tasks to the ones prompted by the user.        
        """
        for task, event in self.get_uploaded_tasks():
            if event.start is not None and event.end is not None:
                length = round((event.end - event.start).total_seconds() / 60)

                if length != round(task.length.total_seconds() / 60):
                    task.length = timedelta(minutes=length)
            
            if event.summary != task.name:
                task.name = event.summary
            
            if event.description != task.desc + tag:
                task.desc = event.description[:len(tag)]
            
            if event.color_id in [GCColour.BASIL.value, GCColour.SAGE.value]:
                for i,t in enumerate(self.tasks_by_due):
                    if task == t:
                        self.tasks_by_due.pop(i)

                        self.save_events()

    def get_uploaded_tasks(self, filterCompleted=False):
        """
        Gets all uploaded tasks as Tuple(task, event) from Google Calendar as GCSA Events and returns them as a list.
        """
        tasks = []

        for event_id, task in self.uploaded_events:
            event = self.link.get_event(event_id)
            if filterCompleted and event.color_id in [GCColour.BASIL.value, GCColour.SAGE.value]:
                # it's completed (marked as green), skip it
                continue
            
            tasks.append((task,event))

        return tasks
    
    def organise_calendar(self, starting_time = None, skipped_task = None):
        """
        DOES NOT MODIFY self.tasks_by_due

        Creates a valid new calendar, organising tasks by due date and around events.
        
        To be implemented in order of priority:
        1) (Assuming all tasks are assignable easily in the order by due date) lay out all tasks by due date. ✅
        2) Lay out all tasks by due date if tasks can be switched around and still give a valid layout. (ex: short task taking up space on day 2 when day 1 has a gap free for it)
            - do 2 layers of recursion, in which we heuristically swap two random events, check the layout's validity and keep going#
            - if this fails, move onto step 3
        3) Split up tasks into smaller segments (if needed and opted in)
        4) If the layout isn't possible and you're swamped, extend log_off time by increments of 30 minutes (includes log_off time being technically before log_on time, if log_off is 2am and log_on is 7am)
        """

        # let's find the first active moment that's a multiple of 15 minutes after when this is being run

        fifteen_minutes = timedelta(minutes=15)
        if starting_time is None:
            now = datetime.now(local_timezone) 

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
            
            working_time = contextualise(now_time, now)
        else:
            working_time = starting_time

        task_list = [] # tuple(time: starting_time, task: task assigned to this time)

        # keep skipping forwards fifteen minutes until a slot is found which doesn't collide with log_off time and any scheduled events

        tasks_by_due = copy(self.tasks_by_due)

        for _ in range(len(tasks_by_due)):
            task = tasks_by_due.pop(0)

            if task == skipped_task:
                continue
                # task doesn't make it onto the task_list

            while True: # logic to break is too complicated to be handled in a statement
                valid = True

                end = working_time + task.length

                # consider a number line and the intersection of 2 1d segments
                # additionally, if the log_on or log_off lies within working_time and end, it is also invalid (this logic is harder though)

                # if the starting time of the event we are on is after end, then we can break the loop (iterating through events is hard when it goes through the next year's worth)

                for event in self.events:
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

    def reload_tasks(self):
        """
        Reorganises the calendar according to the current event layout.
        """
        
        # if the time is in the middle of a task, organise_calendar will shift this task along infinitely and we don't want that to happen
        # redesign organise_calendar to fit this description

        self.merge_pending() # now the entire list is back together and happy
        self.check_event_updates() # now we're up to date with the server
        self.update_events() # ""

        # find the event that is currently being done. if multiple are currently ongoing, pick the one that started first, and if they both started first, pick the one that ends the first. if then necessary, pick the one with the earliest name alphabetically.

        now = datetime.now(local_timezone)

        matches = []
        for task, event in self.get_uploaded_tasks(True):
            # if the task isn't completed and we are currently in the middle of it, attach it as a match

            if event.end > now and event.start <= now:
                matches.append((task,event))
        
        currently_doing = None
        
        if len(matches) > 1:
            result1 = sorted(matches, key=lambda x: x[1].start)
            
            starting_time = None
            result2 = []
            for task, event in result1:
                if starting_time is None:
                    starting_time = event.start
                    result2.append((task,event))
                else:
                    if event.start == starting_time:
                        result2.append((task,event))
                    else:
                        break
            
            if len(result2) > 1:
                result3 = sorted(result2, key=lambda x: x[1].end)

                ending_time = None
                result4 = []
                for task, event in result3:
                    if ending_time is None:
                        ending_time = event.end
                        result4.append((task,event))
                    else:
                        if event.end == ending_time:
                            result4.append((task,event))
                        else:
                            break
                
                if len(result4) > 1:
                    result5 = sorted(result4, key=lambda x: x[1].summary)

                    matches = [result5[0]]
            else:
                matches = result2
        
        if len(matches) == 1:
            currently_doing = matches[0]
        
        # now we have the currently doing event if it exists, we can now try reorganise

        if currently_doing is None:
            task_list = self.organise_calendar()
        else:
            # custom organise in which the starting_time is determined, as well as the first task being removed
            starting_time = currently_doing[1].end # start when this ends
            
            task_list = self.organise_calendar(starting_time=starting_time, skipped_task=currently_doing[0])

            # let's make the check now to see if we're in the time period to notify

            notify_time = starting_time - timedelta(minutes=notify_before_warning)
            td = timedelta(seconds=(self.refresh_rate+1)/2)

            lbound = notify_time - td
            ubound = notify_time + td

            current_time = datetime.now(local_timezone) 
            if lbound <= current_time and current_time <= ubound:
                # if the task is still red
                if currently_doing.color_id == GCColour.TOMATO.value:
                    # send notification

                    self.notify.send(f"Your current task ends in 5 minutes. If you have completed it, change it to green now.")
        
        # now check the task list timings against the uploaded ones

        deleted_events = []
        for task1, event in self.get_uploaded_tasks(False):
            if currently_doing is not None and task1 == currently_doing[0]:
                continue

            i = 0
            found = False
            for time, task2 in task_list:
                # Only if the tasks are exactly equivalent and the uploaded event matches task2 will we skip uploading this
                # In that case remove this item from task list, and do not add it to be deleted

                if task1 == task2 and task2.name == event.summary and task2.length == (event.end - event.start) and task2.desc + tag == event.description and time == event.start:
                    task_list.pop(i)

                    # match has been found
                    found = True
                    break
                
                i += 1
            
            if found is False:
                deleted_events.append(event.event_id)
        
        # now delete all the events that didn't match

        for event_id in deleted_events:
            self.link.delete_event(event_id)

            # remove these uploaded events from the uploaded events list as well

            i=0
            for eid, task in self.uploaded_events:
                if eid == event_id:
                    self.uploaded_events.pop(i)
                    continue # i would be incremented but then the list length shortens

                i+=1
        
        # now upload task list

        self.upload_task_list(task_list)

        self.save_events()

        # done!
