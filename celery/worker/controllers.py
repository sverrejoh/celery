"""

Worker Controller Threads

"""
from celery.backends import default_periodic_status_backend
from datetime import datetime
from multiprocessing import get_logger
from multiprocessing.queues import Empty as QueueEmpty
import multiprocessing
import threading
import time


class BackgroundProcess(multiprocessing.Process):
    """Process running an infinite loop which for every iteration
    calls its :meth:`on_iteration` method.

    This also implements graceful shutdown of the thread by providing
    the :meth:`stop` method.

    """
    is_infinite = True

    def __init__(self):
        super(BackgroundProcess, self).__init__()
        self.daemon = True

    def run(self):
        """This is the body of the thread.

        To start the thread use :meth:`start` instead.

        """
        while self.is_infinite:
            self.on_iteration()

    def on_iteration(self):
        """This is the method called for every iteration and must be
        implemented by every subclass of :class:`BackgroundProcess`."""
        raise NotImplementedError(
                "InfiniteThreads must implement on_iteration")

    def stop(self):
        """Gracefully shutdown the thread."""
        self.terminate()


class Mediator(BackgroundProcess):
    """Process continuously sending tasks in the queue to the pool.

    .. attribute:: bucket_queue

        The task queue, a :class:`Queue.Queue` instance.

    .. attribute:: callback

        The callback used to process tasks retrieved from the
        :attr:`bucket_queue`.

    """

    def __init__(self, bucket_queue, callback):
        super(Mediator, self).__init__()
        self.bucket_queue = bucket_queue
        self.callback = callback

    def on_iteration(self):
        logger = get_logger()
        try:
            logger.debug("Mediator: Trying to get message from bucket_queue")
            # This blocks until there's a message in the queue.
            task = self.bucket_queue.get(timeout=1)
        except QueueEmpty:
            logger.debug("Mediator: Bucket queue is empty.")
            pass
        else:
            logger.debug("Mediator: Running callback for task: %s[%s]" % (
                task.task_name, task.task_id))
            self.callback(task)


class PeriodicWorkController(BackgroundProcess):
    """A thread that continuously checks if there are
    :class:`celery.task.PeriodicTask` tasks waiting for execution,
    and executes them. It also finds tasks in the hold queue that is
    ready for execution and moves them to the bucket queue.

    (Tasks in the hold queue are tasks waiting for retry, or with an
    ``eta``/``countdown``.)

    """

    def __init__(self, bucket_queue, hold_queue):
        super(PeriodicWorkController, self).__init__()
        self.hold_queue = hold_queue
        self.bucket_queue = bucket_queue

    def on_iteration(self):
        logger = get_logger()
        logger.debug("PeriodicWorkController: Running periodic tasks...")
        self.run_periodic_tasks()
        logger.debug("PeriodicWorkController: Processing hold queue...")
        self.process_hold_queue()
        logger.debug("PeriodicWorkController: Going to sleep...")
        time.sleep(1)

    def run_periodic_tasks(self):
        default_periodic_status_backend.run_periodic_tasks()

    def process_hold_queue(self):
        """Finds paused tasks that are ready for execution and move
        them to the :attr:`bucket_queue`."""
        logger = get_logger()
        try:
            logger.debug(
                "PeriodicWorkController: Getting next task from hold queue..")
            task, eta = self.hold_queue.get_nowait()
        except QueueEmpty:
            logger.debug("PeriodicWorkController: Hold queue is empty")
            return
        if datetime.now() >= eta:
            logger.debug(
                "PeriodicWorkController: Time to run %s[%s] (%s)..." % (
                    task.task_name, task.task_id, eta))
            self.bucket_queue.put(task)
        else:
            logger.debug(
                "PeriodicWorkController: ETA not ready for %s[%s] (%s)..." % (
                    task.task_name, task.task_id, eta))
            self.hold_queue.put((task, eta))
