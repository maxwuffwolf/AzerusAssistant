import logging

class TkinterQueueHandler(logging.Handler):
    """
    Logging handler that puts log records into a queue for the Tkinter thread.
    """
    def __init__(self, queue):
        super().__init__()
        self.queue = queue

    def emit(self, record):
        try:
            self.queue.put(record)
        except Exception:
            self.handleError(record)