import os
import subprocess
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

token = os.environ.get("GITHUB_TOKEN")
repo_name = "ReviewSentinel"
username = "NithinGJ2005"
cwd = r"c:\Users\Nithin G J\Desktop\Code Review Agent"

print("Checking if git is initialized...")
if not os.path.exists(os.path.join(cwd, ".git")):
    subprocess.run(["git", "init"], cwd=cwd, check=True)

# Create a proper .gitignore if it doesn't exist
gitignore_path = os.path.join(cwd, ".gitignore")
if not os.path.exists(gitignore_path):
    with open(gitignore_path, "w") as f:
        f.write(".env\n*.pyc\n__pycache__/\n.pytest_cache/\nreview_sentinel.egg-info/\nbuild/\ndist/\ndata/\n")

print("Configuring local git config...")
subprocess.run(["git", "config", "user.name", "NithinGJ2005"], cwd=cwd)
subprocess.run(["git", "config", "user.email", "nithingj2005@gmail.com"], cwd=cwd)

print("Creating repository on GitHub...")
headers = {
    "Authorization": f"token {token}",
    "Accept": "application/vnd.github.v3+json"
}
payload = {
    "name": repo_name,
    "description": "ReviewSentinel - AI-Powered Autonomous Code Review Agent using LangGraph and Gemini",
    "private": False
}
r = requests.post("https://api.github.com/user/repos", json=payload, headers=headers)
if r.status_code == 201:
    print("Repository created successfully on GitHub!")
elif r.status_code == 422:
    print("Repository already exists on GitHub. Proceeding to push changes.")
else:
    print(f"Failed to create repository: {r.status_code} - {r.text}")

print("Staging and committing files...")
subprocess.run(["git", "add", "."], cwd=cwd, check=True)
# Commit might fail if there's nothing to commit, we catch it
try:
    subprocess.run(["git", "commit", "-m", "Initial commit of ReviewSentinel agent"], cwd=cwd, check=True)
except Exception:
    print("Nothing to commit or already committed.")

print("Setting up remote origin and pushing...")
# Remove origin if it already exists
subprocess.run(["git", "remote", "remove", "origin"], cwd=cwd)
remote_url = f"https://x-access-token:{token}@github.com/{username}/{repo_name}.git"
subprocess.run(["git", "remote", "add", "origin", remote_url], cwd=cwd, check=True)

subprocess.run(["git", "branch", "-M", "main"], cwd=cwd, check=True)
subprocess.run(["git", "push", "-u", "origin", "main", "--force"], cwd=cwd, check=True)
print("Code pushed successfully!")
