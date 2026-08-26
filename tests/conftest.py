import os

os.environ["WAN_TEST_MODE"] = "1"
os.environ.setdefault("DASHSCOPE_API_KEY", "test-key-not-real")
os.environ.setdefault("WAN_WORKSPACE_ID", "test-workspace")
os.environ.setdefault("WAN_REGION", "singapore")
