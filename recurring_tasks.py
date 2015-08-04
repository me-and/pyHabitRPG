#!/usr/bin/env python3
from datetime import timedelta, datetime, timezone
from numbers import Integral, Real, Number
import sys
from functools import total_ordering
from abc import ABCMeta, abstractmethod
from collections import defaultdict

import yaml

import habitrpg

# For this to work, I needed to apply the following patch to yaml's
# constructor.py.  Should probably work out a better way of doing that than
# patching the actual library...
'''
--- old/constructor.py  2015-08-04 01:56:48.735687086 +0100
+++ new/constructor.py      2015-08-04 01:56:29.295463976 +0100
@@ -395,7 +395,7 @@
     def construct_yaml_map(self, node):
         data = {}
         yield data
-        value = self.construct_mapping(node)
+        value = self.construct_mapping(node, deep=True)
         data.update(value)

     def construct_yaml_object(self, node, cls):
'''

class Sentinel(object):
    _instances = {}
    def __new__(cls, name, truth=True):
        if name in cls._instances:
            return cls._instances[name]
        else:
            return super().__new__(cls)

    def __init__(self, name, truth=True):
        super().__init__(self)
        self._name = name
        self._instances[name] = self
        self._truth = truth

    def __repr__(self):
        if self._truth:
            return '{}({!r})'.format(self.__class__.__name__, self._name)
        else:
            return '{}({!r}, {!r})'.format(
                    self.__class__.__name__, self._name, self._truth)

    def __str__(self):
        return str(self._name)

    def __bool__(self):
        return self._truth


@total_ordering
class Counter(Integral):
    def __init__(self, count=0):
        self.count = int(count)

    def __eq__(self, other):
        return self.count == other

    def __lt__(self, other):
        return self.count <  other

    def __le__(self, other):
        return self.count <= other


    def __pos__(self):
        return self.__class__(+self.count)

    def __neg__(self):
        return self.__class__(-self.count)

    def __abs__(self):
        return self.__class__(abs(self.count))

    def __invert__(self):
        return self.__class__(~self.count)

    def __add__(self, other):
        return self.__class__(self.count + other)

    def __mul__(self, other):
        return self.__class__(self.count * other)

    def __mod__(self, other):
        return self.__class__(self.count % other)

    def __pow__(self, other):
        return self.__class__(self.count ** other)

    def __floordiv__(self, other):
        return self.__class__(self.count // other)

    def __truediv__(self, other):
        return self.__class__(self.count / other)

    def __radd__(self, other):
        return self.__class__(other + self.count)

    def __rmul__(self, other):
        return self.__class__(other * self.count)

    def __rmod__(self, other):
        return self.__class__(other % self.count)

    def __rpow__(self, other):
        return self.__class__(other ** self.count)

    def __rfloordiv__(self, other):
        return self.__class__(other // self.count)

    def __rtruediv__(self, other):
        return self.__class__(other / self.count)

    def __and__(self, other):
        return self.__class__(self.count & other)

    def __or__(self, other):
        return self.__class__(self.count | other)

    def __xor__(self, other):
        return self.__class__(self.count ^ other)

    def __lshift__(self, other):
        return self.__class__(self.count << other)

    def __rshift__(self, other):
        return self.__class__(self.count >> other)

    def __rand__(self, other):
        return self.__class__(other & self.count)

    def __ror__(self, other):
        return self.__class__(other | self.count)

    def __rxor__(self, other):
        return self.__class__(other ^ self.count)

    def __rlshift__(self, other):
        return self.__class__(other << self.count)
    def __rrshift__(self, other):
        return self.__class__(other >> self.count)

    def __ceil__(self):
        return self

    def __floor__(self):
        return self

    def __round__(self, *args, **kwargs):
        rounded = round(self.count, *args, **kwargs)
        if isinstance(Integeral, rounded):
            return self.__class__(rounded)
        else:
            return rounded

    def __int__(self):
        return int(self.count)

    def __trunc__(self):
        return self.count.__trunc__()

    def __str__(self):
        return self.count.__str__()

    def __repr__(self):
        return "%s(%d)" % (self.__class__.__name__, self.count)

    def reset(self, count=0):
        self.counter = count


class Trigger(object, metaclass=ABCMeta):
    @abstractmethod
    def __hash__(self):
        raise NotImplementedError

    @abstractmethod
    def __eq__(self):
        raise NotImplementedError

    @abstractmethod
    def triggered(self):
        raise NotImplementedError


class TaskTrigger(Trigger):
    def __init__(self, task):
        self.task = task
        super().__init__()

    def __hash__(self):
        return hash((self.task, self.__class__))

    def __eq__(self, other):
        try:
            return (self.task, self.__class__) == (other.task, other.__class__)
        except AttributeError:
            return False


class TaskCompletionTrigger(TaskTrigger):
    def triggered(self):
        try:
            self.task.fetch()
        except habitrpg.requests.exceptions.HTTPError as ex:
            if ex.response.status_code == 404:
                return WILL_NEVER_TRIGGER
            else:
                raise ex

        return self.task.completed


class TaskDeletionTrigger(TaskTrigger):
    def triggered(self):
        try:
            self.task.fetch()
        except habitrpg.requests.exceptions.HTTPError as ex:
            if ex.response.status_code == 404:
                return True
            else:
                raise ex

        if self.task.completed:
            return WILL_NEVER_TRIGGER

        return False


class TimeTrigger(Trigger):
    def __init__(self, time):
        self.time = time
        super().__init__()

    def __hash__(self):
        return hash((self.time, self.__class__))

    def __eq__(self, other):
        try:
            return (self.time, self.__class__) == (other.time, other.__class__)
        except AttributeError:
            return False

    def triggered(self):
        try:
            # First try a naive comparison.
            return self.time <= datetime.now()
        except TypeError:
            # If that doesn't work, self.time was timezone-aware, so use a
            # timezone-aware comparison.
            return self.time <= datetime.now(timezone.utc)


class CountTrigger(Trigger):
    def __init__(self, target):
        self.counter = Counter(0)
        self.target = target
        super().__init__()

    def __hash__(self):
        # The value of self.counter may change, but what we're actually
        # interested in for the purposes of hashes is which counter it is,
        # which `id` gives us a unique value for.
        return hash((self.target, id(self.counter), self.__class__))

    def __eq__(self, other):
        try:
            return (self.target, id(self.counter), self.__class__)
        except AttributeError:
            return False

    def triggered(self):
        return counter >= target


class Action(object, metaclass=ABCMeta):
    @abstractmethod
    def __call__(self):
        raise NotImplementedError


class CounterAction(Action, metaclass=ABCMeta):
    def __init__(self, counter):
        self.counter = counter

class IncrementCounter(Action):
    def __init__(self, counter, amount=1):
        self.amount = amount
        super().__init__(self, counter)

    def __call__(self):
        self.counter += amount


class ResetCounter(Action):
    def __call__(self):
        self.counter.reset()


class Todo(object):
    def __init__(self, title, notes=None, value=None, priority=None, tags=None,
            checklist=None, due=None):
        self.title = title
        self.notes = notes
        self.value = value
        self.priority = priority
        self.tags = tags
        self.checklist = checklist
        self.due = due


class TodoAction(Action, metaclass=ABCMeta):
    def __init__(self, user, todo):
        self.user = user
        self.todo = todo

    @abstractmethod
    def __call__(self, *args, **kwargs):
        raise NotImplementedError

class CreateTodo(TodoAction):
    def __init__(self, user, todo, triggers,
            completion_actions=None, deletion_actions=None):
        self.completion_actions = completion_actions
        self.deletion_actions = deletion_actions
        super().__init__(user, todo)

    def __call__(self):
        if isinstance(timedelta, self.todo.due):
            due = datetime.utcnow() + self.todo.due
        else:
            due = self.todo.due

        new_task = habitrpg.Todo.new(
                self.user,
                self.todo.title,
                self.todo.notes,
                self.todo.value,
                self.todo.priority,
                self.todo.tags,
                self.todo.checklist,
                due)

        if completion_actions:
            triggers[
                    TaskCompletionTrigger(new_task)].extend(completion_actions)
        if deletion_actions:
            triggers[TaskDeletionTrigger(new_task)].extend(deletion_actions)


class ScheduleTodo(TodoAction):
    def __init__(self, user, todo, triggers, creation_time,
            completion_actions=None, deletion_actions=None):
        self.triggers = triggers
        self.creation_time = creation_time
        self.completion_actions = completion_actions
        self.deletion_actions = deletion_actions
        super().__init__(user, todo)

    def __call__(self):
        if isinstance(timedelta, self.creation_time):
            creation_time = datetime.utcnow() + self.creation_time
        else:
            creation_time = self.creation_time
        self.triggers[TimeTrigger(creation_time)].append(
                CreateTodo(self.user, self.todo, self.triggers,
                    self.completion_actions, self.deletion_actions))


WILL_NEVER_TRIGGER = Sentinel('Will never trigger', truth=False)

def run_triggers(triggers):
    for trigger in triggers.copy():
        triggered = trigger.triggered()
        if triggered:
            actions = triggers.pop(trigger)
            for action in actions:
                action()
        elif triggered is WILL_NEVER_TRIGGER:
            del triggers[trigger]


if __name__ == '__main__':
    user = habitrpg.User.from_file()
    triggers = {}  # Using defaultdict here would be ideal, but yaml really doesn't like that.
    yaml.add_representer(habitrpg.User, lambda u, a: u.represent_scalar('!user', ''))
    yaml.add_constructor('!user', lambda l, n: habitrpg.User.from_file())
    t = Todo('Testing testing 123')
    s = ScheduleTodo(user, t, triggers, timedelta(hours=4), deletion_actions=[ScheduleTodo(user, t, triggers, timedelta(minutes=3))])
    s.completion_actions = [s]
    c = CountTrigger(2)
    triggers[c] = s
    print(yaml.dump(triggers))
    print(yaml.load(yaml.dump(triggers)))
