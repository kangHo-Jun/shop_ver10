import sys
import os

# Set up paths
sys.path.append(os.getcwd())

print("Loading modules...")
try:
    import v4_auto_server
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

print("Modules loaded. calling run_batch_process...")

# Mocking Flask context if needed? V4 doesn't use app context in logic.
# But run_batch_process uses 'lock' and 'browser_manager'.
# They are in v4_auto_server module scope.

try:
    result = v4_auto_server.run_batch_process()
    print(f"Result: {result}")
except Exception as e:
    print(f"CRASH: {e}")
    import traceback
    traceback.print_exc()
