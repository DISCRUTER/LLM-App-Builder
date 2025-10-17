# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "fastapi[standard]",
#   "uvicorn",
#   "requests",
#   "google-genai",
#   "pydantic",
# ]
# ///

import os
import json
import time
import base64
import requests
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, ValidationError
from google.genai import Client

# Secrets and Keys

OWNER = "24f2004631"
GITHUB_API_KEY = os.getenv("GITHUB_PAT")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SECRET = os.getenv("SECRET_KEY")

app = FastAPI(title="LLM-Assisted App Builder")
GITHUB_HEADER = {
    "Authorization": f"Bearer {GITHUB_API_KEY}",
    "Accept": "application/vnd.github+json",
}

# Pydantic Models
class Attachment(BaseModel):
    name: str
    url: str # Data URI

class Request(BaseModel):
    email: str
    secret: str
    task: str
    round: int
    nonce: str
    brief: str
    checks: List[str]
    evaluation_url: str
    attachments: Optional[List[Attachment]] = []

# Helper Functions
def CheckSecretKey(key: str) -> None:
    # Check if the secret key matches
    if key != SECRET:
        raise HTTPException(status_code=401, detail="Invalid secret key")

def GetRepoName(task: str, nonce: str) -> str:
    return f"{task}_{nonce}"

def GetGithubPagesURL(repoName: str) -> str:
    return f"https://{OWNER}.github.io/{repoName}/"

# Github Opertations
def CreateGithubRepo(repoName: str):
    payload = {
        "name": repoName,
        "private": False,
        "auto_init": True,
        "license_template": "mit",
    }

    response = requests.post("https://api.github.com/user/repos", json=payload, headers=GITHUB_HEADER)

    if response.status_code not in (201, 422):
        raise Exception(f"Failed to create repository: {response.status_code}, {response.text}")
    
    return response.json().get("html_url", f"https://github.com/{OWNER}/{repoName}")

def EnablePages(repoName: str):
    payload = {
        "source": {
            "branch": "main",
            "path": "/"
        },
    }

    response = requests.post(f"https://api.github.com/repos/{OWNER}/{repoName}/pages", json=payload, headers=GITHUB_HEADER)
    
    if response.status_code not in (201, 409):
        raise Exception(f"Failed to enable pages: {response.status_code}, {response.text}")

def GetFileSHA(repoName: str, fileName: str) -> Optional[str]:
    # Gets the SHA of an existing file, or None if it doesn't exist
    response = requests.get(f"https://api.github.com/repos/{OWNER}/{repoName}/contents/{fileName}", headers=GITHUB_HEADER)

    if response.status_code == 200:
        return response.json().get("sha")
    return None

def GetFileContent(repoName: str, fileName: str) -> Optional[str]:
    # Gets the decoded content of an existing file
    response = requests.get(f"https://api.github.com/repos/{OWNER}/{repoName}/contents/{fileName}", headers=GITHUB_HEADER)

    if response.status_code == 200 and response.json().get("encoding") == "base64":
        content = response.json().get("content", "")
        return base64.b64decode(content).decode('utf-8')
    return None

def GetExistingFiles(repoName: str) -> List[Dict[str, Any]]:
    # Lists all files in the root of the repository
    response = requests.get(f"https://api.github.com/repos/{OWNER}/{repoName}/contents/", headers=GITHUB_HEADER)
    existingFiles = {}

    if response.status_code == 200:
        contents =  response.json()  # List of file dicts
        for item in contents:
            if item["type"] == "file" and any(item["name"].endswith(ext) for ext in ["html", "css", "js", "md", "json"]):
                # Fetch file content
                fileContent = GetFileContent(repoName, item["path"])
                if fileContent:
                    existingFiles[item["path"]] = fileContent
    return existingFiles

def PushToRepo(repoName: str, round: int, files: list[dict]) -> str:
    latestSHA = ""
    for file in files:
        fileName = file.get("name")
        fileContent = file.get("content")  # Base64 encoded content
        if not fileName or not fileContent:
            continue

        fileSHA = GetFileSHA(repoName, fileName)
        action = "Update" if fileSHA else "Create"
        
        payload = {
            "message": f"Round {round}-{action} {fileName}",
            "content": fileContent,  # Base64 encoded content
        }

        if fileSHA:
            payload["sha"] = fileSHA
        
        response = requests.put(f"https://api.github.com/repos/{OWNER}/{repoName}/contents/{fileName}", json=payload, headers=GITHUB_HEADER)

        if response.status_code in (200, 201):
            latestSHA = response.json().get("commit", {}).get("sha", latestSHA)
        else:
            print(f"Failed to {action} {fileName}: {response.status_code}, {response.text}")
        print(f"Push {fileName} response:", response.json())
    
    if not latestSHA:
        raise Exception("No files were pushed successfully.")

    return latestSHA

# LLM Code Generation

def LLMCode(requestData: Request, existingFiles: Dict) -> List[Dict[str, str]]:
    """
    Generates code using the Gemini API and formats it for PushToRepo.
    
    The function asks Gemini to return a JSON object containing a list 
    of file details, which is then processed and base64 encoded.
    """

    client = Client(api_key=GEMINI_API_KEY)

    # Context/Existing Files
    contextSection = []

    # Exsiting files for round 2
    if existingFiles:
        contextSection.append("--- EXISTING REPO FILES (DO NOT DELETE UNLESS REPLACING) ---")
        for fileName, content in existingFiles.items():
            contextSection.append(f"\nFile: {fileName}\n```\n{content}\n```\n")
    
    # Check for attachments
    if requestData.attachments:
        contextSection.append("\n\n--- ATTACHMENTS (DATA URIs) ---")
        for attachment in requestData.attachments:
            try:
                _, encodedData = attachment.url.split(";base64,")
                decodedContent = base64.b64decode(encodedData).decode('utf-8')
                contextSection.append(f"\nATTACHMENT: {attachment.name} ({attachment.url.split(';')[0]})\nContent :\n{decodedContent}\n")
            except Exception as e:
                print(f"Failed to decode attachment {attachment.name}: {e}")
    
    # System instruction to force JSON output
    systemInstruction = "You must return a single, well-formed JSON array of file objects. Do not include any text outside the JSON block."

    fullPrompt = (
        f"You are an expert web developer creating an app for task '{requestData.task}'. "
        f"Your current round is {requestData.round}. "
        f"The primary goal is to **{requestData.brief}**. "
        f"The final files must satisfy these checks: {requestData.checks}. "
        f"{'\n'.join(contextSection)}"
        f"\n\nReturn a JSON array of objects. Each object must have a 'name' (filename, e.g., 'index.html', 'LICENSE') "
        f"and 'content' (the file's raw, unencoded string content). "
        f"For Round 1, include 'LICENSE' (MIT) and 'README.md'. For Round 2, only include modified or new files."
    )

    try:
        # 2. Make API Call
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=fullPrompt,
            config={
                "system_instruction": systemInstruction,
                "response_mime_type": 'application/json'
            }
        )
        # 3. Parse JSON response (This line defines the variable generatedFilesData)
        generated_files_data = json.loads(response.text)
    except Exception as e:
        print("Error parsing Gemini response:", e)
        htmlContent = "<html><body><h1>Gemini code generation failed</h1></body></html>"
        return [
            {
                "name" : "error.html",
                "content" : base64.b64encode(htmlContent.encode('utf-8')).decode('utf-8')
            }
        ]

    # Process and encode files
    encoded_files = []
    # If the API call succeeded, generated_files_data is defined
    if isinstance(generated_files_data, list):
        for file in generated_files_data: 
            name = file.get("name")
            content = file.get("content")
            if name and content:
                encoded_files.append({
                    "name": name,
                    "content": base64.b64encode(content.encode('utf-8')).decode('utf-8'),
                })
    
    # Ensure LICENSE and README.md are included in Round 1 if not generated
    if requestData.round == 1 and not any(f.get('name') in ('LICENSE', 'README.md') for f in encoded_files):
        print("Adding default LICENSE/README for Round 1.")
        if not any(f.get('name') == 'LICENSE' for f in encoded_files):
             encoded_files.append({"name": "LICENSE", "content": base64.b64encode("MIT License...".encode()).decode()})
        if not any(f.get('name') == 'README.md' for f in encoded_files):
             encoded_files.append({"name": "README.md", "content": base64.b64encode(f"# Task {requestData.task}\nBrief: {requestData.brief}".encode()).decode()})
    
    return encoded_files

# Evaluation Ping

def PostToEvaluationAPI(requestData: Request, repoDetails: Dict[str, str]):
    payload = {
        "email": requestData.email,
        "task": requestData.task,
        "round": requestData.round,
        "nonce": requestData.nonce,
        "repo_url": repoDetails.get("repoURL"),
        "commit_sha": repoDetails.get("commitSHA"),
        "pages_url": repoDetails.get("pagesURL"),
    }

    headers = {"Content-Type": "application/json"}
    maxRetries = 5
    delay = 1

    print(f"--- Pinging Evaluation API (Round {requestData.round}): {requestData.evaluation_url} ---")

    for attempt in range(maxRetries):
        try:
            response = requests.post(requestData.evaluation_url, json=payload, headers=headers, timeout=15)
            if response.status_code == 200:
                print("Successfully notified evaluation API.")
                return
            else:
                print(f"Evaluation API responded with status {response.status_code}: {response.text}")
        except Exception as e:
            print(f"Error contacting evaluation API: {e}")

        print(f"Retrying in {delay} seconds...")
        if attempt < maxRetries - 1:
            time.sleep(delay)
            delay *= 2  # Exponential backoff

    print("Failed to notify evaluation API after multiple attempts.")

# Core logic for deifferent rounds

def ProcessTaskInBackground(requestData: Request):
    repoName = GetRepoName(requestData.task, requestData.nonce)

    try:
        if requestData.round == 1:
            repoURL = CreateGithubRepo(repoName)
        else:
            repoURL = f"https://github.com/{OWNER}/{repoName}"
        
        existingFiles = {}
        if requestData.round == 2:
            existingFiles = GetExistingFiles(repoName)
            print(f"Found {len(existingFiles)} files for revision context.")

        filesToCommit = LLMCode(requestData, existingFiles)

        if not filesToCommit:
            raise Exception("No files generated by LLM.")
        
        commitSHA = PushToRepo(repoName, requestData.round, filesToCommit)

        EnablePages(repoName)
        pagesURL = GetGithubPagesURL(repoName)

        repoDetails = {
            "repoURL": repoURL,
            "commitSHA": commitSHA,
            "pagesURL": pagesURL,
        }

        PostToEvaluationAPI(requestData, repoDetails)
    
    except Exception as e:
        print(f"Error processing task: {e}")

# Endpoints

@app.post("/")
async def HandleTask(requestData: Request, backgroundTasks: BackgroundTasks):
    try:
        CheckSecretKey(requestData.secret)
    except HTTPException as e:
        raise e
    except ValidationError as e:
        return HTTPException(status_code=400, detail="Invalid request data")

    backgroundTasks.add_task(ProcessTaskInBackground, requestData)

    return {
        "status": "success",
        "task": requestData.task,
        "round": requestData.round,
        "message": "Your request is being processed in the background."
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
