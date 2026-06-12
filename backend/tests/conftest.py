import os
# Surface LangGraph msgpack type errors now rather than on a future version upgrade
os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")
