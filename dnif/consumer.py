import logging
import threading
from Queue import Queue, Full

import requests


class Consumer(object):
    def send(self, data):
        raise NotImplementedError


class AsyncHttpConsumer(Consumer):
    """Consumer that uploads logs to the specified endpoint using HTTP.
    Uploads happen in the background to minimally impact caller performance
    """

    def __init__(self, url, buffer_size=1024):
        """
        Initialize the Consumer
        :param url: The target URL
        :param buffer_size: Max number of pending payloads to hold (in memory).
        If the queue is full, further payloads will be dropped
        """
        self._url = url
        self._timeout = 15
        self._queue = Queue(maxsize=buffer_size)
        self._logger = logging.getLogger('dnif.consumer.http')

        # TODO: This shouldn't be a Daemon and should listen for shutdown events.
        self._thread = threading.Thread(target=self._upload)
        self._thread.daemon = True
        self._thread.start()

    def _validate(self, data):
        """ Validate that data does not contain nexted JSON objects. Lists are allowed. """
        for key, value in data.items():
            if isinstance(value, dict):
                self._logger.info('Skipping sending data packet. Nested JSON objects are not allowed: {0}'.format(data))
                return False
        return True

    def send(self, data):
        """ Send the data to the target endpoint.
        This method only queues the upload, the upload itself happens asynchronously in the background.

        :param data: Data to upload. Can be dict (key-value pairs) indicating one log statement, or a list of these
        """
        if isinstance(data, dict):
            data = [data] if self._validate(data) else []
        elif isinstance(data, list):
            data = [d for d in data if self._validate(d)]
        else:
            self._logger.info('Skipping sending data packet. Data must be JSON object: {0}'.format(data))

        try:
            self._queue.put(data, block=False)
        except Full:
            self._logger.info('Dropping data because max buffer size reached: {0}'.format(data))

    def _upload(self):
        while True:
            # TODO: Batch payloads and send as one request
            payload = self._queue.get(block=True)
            try:
                requests.post(self._url, json=payload, timeout=self._timeout)
            except Exception as ex:
                self._logger.info('Error uploading log: {0}'.format(ex))
