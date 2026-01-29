import os
from redis import Redis
from rq import Queue

# Redis Queue (RQ) ka client, jobs line mein lagane ke liye
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

queue = Queue(connection=Redis(
    host=REDIS_HOST,
    port=REDIS_PORT
))