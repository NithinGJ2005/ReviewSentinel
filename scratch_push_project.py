import os
import subprocess
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

token = os.environ.get("GITHUB_TOKEN")
repo_name = "ReviewSentinel"
username = "NithinGJ2005"
cwd = r"c:\Users\Nithin G J\Desktop\Code Review Agent"

print("Staging files without .github folder...")
subprocess.run(["git", "add", "."], cwd=cwd, check=True)
# Untrack .github folder to prevent workflow scope authentication failure
subprocess.run(["git", "rm", "-r", "--cached", ".github"], cwd=cwd)

try:
    subprocess.run(["git", "commit", "-m", "Initial commit of ReviewSentinel agent (without workflows)"], cwd=cwd, check=True)
except Exception:
    print("Nothing to commit or already committed.")

print("Setting up remote origin and pushing...")
remote_url = f"https://x-access-token:{token}@github.com/{username}/{repo_name}.git"
subprocess.run(["git", "remote", "set-url", "origin", remote_url], cwd=cwd)

subprocess.run(["git", "branch", "-M", "main"], cwd=cwd, check=True)
subprocess.run(["git", "push", "-u", "origin", "main", "--force"], cwd=cwd, check=True)
print("Code pushed successfully without workflows!")
