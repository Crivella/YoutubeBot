"""Handler a message queue that allows playing of songes as a pipeline of operations."""
import logging
import queue
import threading
import time
from typing import Callable, Hashable, Iterable, Union

logger = logging.getLogger('bot')

class Pipeline:
    """Pipeline class to handle operations on messages."""
    def __init__(self, operations: Iterable):
        """Create a new pipeline."""
        self.idx = 0
        self.operations: Iterable[tuple[Callable, str, str]] = []
        for tpl in operations:
            try:
                iter(tpl)
            except TypeError:
                tpl = [tpl]
            app = (list(tpl) + [None] * 2)[:3]
            self.operations.append(app)

        self.validate()

    def validate(self):
        for func, extract, pass_mode in self.operations:
            if not callable(func):
                raise ValueError(f'Invalid operation {func}')
            if extract:
                if extract.startswith('cls_attr'):
                    if not len(extract.split(':')) == 2:
                        raise ValueError(f'Invalid extract {extract}')
                elif extract != 'as_is':
                    raise ValueError(f'Invalid extract {extract}')
            if pass_mode:
                if pass_mode.startswith('kwarg'):
                    if not len(pass_mode.split(':')) == 2:
                        raise ValueError(f'Invalid pass_mode {pass_mode}')
                elif pass_mode != 'arg':
                    raise ValueError(f'Invalid pass_mode {pass_mode}')

    @property
    def done(self) -> bool:
        """Whether the pipeline is done or not."""
        return self.idx >= len(self.operations)

    def step(self, previous = None):
        """Perform the next operation in the pipeline."""
        if self.idx >= len(self.operations):
            return previous

        func, extract, pass_mode = self.operations[self.idx]

        args = []
        kwargs = {}
        if extract:
            if extract == 'as_is':
                pass
            elif extract == 'cls_attr':
                key = extract.split(':')[1]
                previous = getattr(previous, key)

        if pass_mode:
            if pass_mode == 'arg':
                args.append(previous)
            elif pass_mode.startswith('kwarg'):
                key = pass_mode.split(':')[1]
                kwargs[key] = previous
            else:
                raise ValueError(f'Invalid pass_mode {pass_mode}')

        try:
            res = func(*args, **kwargs)
        except Exception as exc:
            logger.error(f'Error in pipeline step {self.idx} inputs {previous}', exc_info=True)
            return exc
        else:
            if extract:
                if extract == 'as_is':
                    return res
                elif extract == 'cls_attr':
                    key = extract.split(':')[1]
                    return getattr(res, key)
                else:
                    raise ValueError(f'Invalid extract {extract}')

            self.idx += 1
            return res

class Message:
    """Message class to handle messages in a queue."""



    class NotHandled(Exception):
        """Dummy object to be used as default response of an unresolved message."""
    
    def __int__(self, msg: dict, pipeline: Pipeline):
        """Create a new message with a handler."""
        self.msg = msg
        if isinstance(pipeline, Pipeline):
            self.pipeline = pipeline
        else:
            self.pipeline = Pipeline(pipeline)
        self.idx = 0

        self._intermidiate = msg
        self._response = Message.NotHandled

    def step(self):
        """Step through the pipeline."""
        if self.pipeline.done:
            return

        

        func, extract, pass_mode = self.pipeline[self.idx]
        args = []
        kwargs = {}
        if pass_mode:
            if pass_mode == 'arg':
                args.append(self._intermidiate)
            elif pass_mode.startswith('kwarg'):
                key = pass_mode.split(':')[1]
                kwargs[key] = self._intermidiate
            else:
                raise ValueError(f'Invalid pass_mode {pass_mode}')

        try:
            res = func(*args, **kwargs)
        except Exception as exc:
            logger.error(f'Error in pipeline step {self.idx} inputs {self._intermidiate}', exc_info=True)
            self._response = exc
            self.idx = len(self.pipeline)
        else:
            if extract:
                if extract == 'as_is':
                    self._intermidiate = res
                elif extract == 'cls_attr':
                    key = extract.split(':')[1]
                    self._intermidiate = getattr(res, key)
                else:
                    raise ValueError(f'Invalid extract {extract}')

            self.idx += 1
            if self.idx == len(self.pipeline):
                self._response = self._intermidiate



    def resolve(self):
        """Resolve the message by calling the handler with the message.
        This operation is synchronous and will block the exection until the handler is done."""
        try:
            self._response = self.handler(*self.msg.get('args', ()), **self.msg.get('kwargs', {}))
        except Exception as exc:
            logger.error(f'Error resolving message {self.msg}', exc_info=True)
            self._response = exc
            # Avoid killing the worker thread
            # raise
        else:
            logger.debug(f'MSG Resolved {self.msg} -> {self._response}')

        # Make sure to dereference the message to avoid keeping raw images in memory
        # since i am gonna keep the message in the queue after it is resolved (for msg caching)
        del self.msg

    @property
    def is_resolved(self) -> bool:
        """Whether the message has been resolved or not."""
        return self._response is not Message.NotHandled

    def set_response(self, response):
        """Set the response of the message."""
        self._response = response

    def response(self, timeout: float = 0, poll: float = 0.2):
        """Get the response of the message.

        Args:
            timeout (float, optional): Timeout in seconds to wait for the message to be resolved.
                Defaults to 0 (no timeout).
            poll (float, optional): Polling interval in seconds. Defaults to 0.2.

        Raises:
            TimeoutError: If the message is not resolved after the timeout.

        Returns:
            Any: The response of the message (return value of the handler called on the msg content).
        """
        start = time.time()

        while not self.is_resolved:

            if time.time() - start > timeout > 0:
                raise TimeoutError('Message resolution timed out')
            time.sleep(poll)

        return self._response

    # def __repr__(self):
    #     return f'Message({self.msg}), Handler: {self.handler.__name__}'

    # def __str__(self):
    #     return f'Message({self.msg}), Handler: {self.handler.__name__}'

    # def __eq__(self, __value: object) -> bool:
    #     if not isinstance(__value, Message):
    #         return False

    #     return all([
    #         self.id_ == __value.id_,
    #         self.msg == __value.msg,
    #         self.handler == __value.handler,
    #     ])

    # def copy(self) -> 'Message':
    #     """Return a copy of the message. Used for tests."""
    #     return Message(
    #         self.id_, dict(self.msg), self.handler,
    #         )

# class Queue(list):
#     """Similar to queue.Queue but do not pop the messages after they are resolved."""
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         self.idx: int = 0
#         self.loop_all: bool = False
#         self.loop_one: bool = False
#         # self.lock = threading.Lock()
#         # self.cond = threading.Condition(self.lock)

#     def put(self, msg: dict, handler: Callable) -> Message:
#         """Put a message in the queue."""
#         # with self.lock:
#         self.append(Message(msg, handler))
#         # self.cond.notify_all()
#         return self[-1]

#     def get(self, block: bool = True, timeout: float = None) -> Message | None:
#         if not self:
#             return None
#         if self.loop_one:
#             return self[self.idx]
#         self.idx += 1
#         if self.idx < 0:
#             self.idx = 0
#         if self.idx >= len(self):
#             if self.loop_all:
#                 self.idx = 0
#             else:
#                 return None
#         return self[self.idx]
#         """Get a message from the queue."""
#         # with self.lock:
#             while not self:
#                 if not block:
#                     raise queue.Empty
#                 # self.cond.wait(timeout=timeout)
#             return self.pop(0)


class Worker():
    """Worker object to be used in WorkerMessageQueue."""
    def __init__(self, attached_queue: list[Message], step_num, poll_interval: float = .2):
        self.queue = attached_queue
        self.idx = 0
        self.step_num = step_num
        self.kill = False
        self.running = False
        self.thread = None
        self.poll_interval = poll_interval

    def _worker(self):
        """Worker function that consumes messages from the queue and resolves them."""
        self.running = True
        while not self.kill:
            if self.idx >= len(self.queue):
                time.sleep(self.poll_interval)
            msg = self.queue[self.idx]
            if msg.idx == self.step_num:
                msg.step()

        self.running = False

    def start(self):
        """Start the worker thread."""
        self.kill = False # Allow restarting the worker
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def stop(self, timeout: float = 2):
        """Stop the worker thread."""
        self.kill = True
        if self.thread is not None:
            self.thread.join(timeout=timeout)
            if self.thread.is_alive():
                logger.warning(f'Worker thread did not stop properly after {timeout} seconds')
        self.thread = None

queues: dict[int, 'WorkerMessageQueue'] = {}

class WorkerMessageQueue():
    """Bundle together the queue and its workers."""
    def __init__(self, *args, step_numm: int, num_workers: int = 1, **kwargs):
        """Create a new WorkerMessageQueue.

        Args:
            num_workers (int, optional): Number of workers to spawn. Defaults to 1.
        """
        self.msg_queue = list()
        self.workers = [Worker(self.msg_queue) for _ in range(num_workers)]

    @classmethod
    def from_server_name(cls, server_id: int, num_workers: int = 1):
        """Create a new WorkerMessageQueue with a server name."""
        if server_id not in queues:
            queues[server_id] = cls(num_workers=num_workers)
        return queues[server_id]

    def put(self, msg: dict, handler: Callable) -> Message:
        """Call the put method of the queue."""
        return self.msg_queue.append(Message(msg, handler))

    def get(self, *args, **kwargs) -> Union[Message, list[Message]]:
        """Call the get method of the queue."""
        return self.msg_queue.get(*args, **kwargs)

    def start_workers(self):
        """Start all the worker threads registered to this queue."""
        for worker in self.workers:
            worker.start()

    def stop_workers(self):
        """Stop all the worker threads registered to this queue."""
        for worker in self.workers:
            worker.stop()
