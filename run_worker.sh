#!/bin/bash
# Set environment variable to fix macOS fork() crash
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES

# Background worker chalao, taaki jobs process ho sakein
source venv/bin/activate
rq worker
