# LLM-Assisted App Builder

This project is a FastAPI-based web service that automates the creation and revision of simple web applications using Google's Gemini Pro. It receives a task description, generates the necessary HTML, CSS, and JavaScript, creates a GitHub repository, pushes the code, and deploys the application using GitHub Pages. The service is designed to work in a two-round process: initial creation (Round 1) and revision (Round 2).

## Features

  - **AI-Powered Code Generation**: Leverages the Google Gemini API to generate web application code from a natural language brief.
  - **Automated GitHub Workflow**: Automatically creates GitHub repositories, commits files, and manages updates.
  - **Instant Deployment**: Deploys the generated web application to GitHub Pages for immediate access.
  - **Asynchronous Processing**: Uses FastAPI's `BackgroundTasks` to handle the entire code generation and deployment process without blocking the server.
  - **Secure Endpoint**: Protects the API endpoint with a shared secret key.
  - **Revision Capability**: Can fetch existing code from a repository to provide context for revisions in a second round.
  - **External Evaluation Hook**: Pings a specified URL upon successful deployment to notify an external evaluation service.

-----

## Prerequisites

Before you begin, ensure you have the following:

  - **Python 3.11** or newer.
  - A **GitHub Account** and a **Personal Access Token (PAT)** with `repo` and `workflow` scopes.
  - A **Google Gemini API Key**. You can get one from [Google AI Studio](https://aistudio.google.com/app/apikey).

-----

## Installation

1.  **Clone the repository** (or save the script as `main.py`):

    ```bash
    git clone <your-repo-url>
    cd <your-repo-url>
    ```

2.  **Install the required dependencies**:

    ```bash
    pip install "fastapi[standard]" uvicorn requests google-genai pydantic
    ```

-----

## Configuration

You need to configure the following credentials and settings within the script or as environment variables.

1.  **Update GitHub Owner**:
    Change the `OWNER` variable in the script to your GitHub username.

    ```python
    OWNER = "your-github-username"
    ```

2.  **Set Environment Variables**:
    It is highly recommended to use environment variables to keep your secrets safe.

      * **Linux/macOS**:

        ```bash
        export GITHUB_PAT="your_github_personal_access_token"
        export GEMINI_API_KEY="your_gemini_api_key"
        export SECRET_KEY="your_strong_secret_key"
        ```

      * **Windows (Command Prompt)**:

        ```cmd
        set GITHUB_PAT="your_github_personal_access_token"
        set GEMINI_API_KEY="your_gemini_api_key"
        set SECRET_KEY="your_strong_secret_key"
        ```

    Alternatively, you can hardcode these values in the script for quick testing, but this is **not recommended for production**.

-----

## Running the Application

Once the configuration is complete, you can start the FastAPI server using Uvicorn.

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

The server will be running and accessible at `http://localhost:8000`.

-----

## API Usage

The application exposes a single endpoint to handle app creation and revision requests.

### Endpoint

`POST /`

This endpoint accepts a JSON payload and initiates the build process as a background task.

### Request Body

| Field            | Type                | Description                                                                 |
| ---------------- | ------------------- | --------------------------------------------------------------------------- |
| `email`          | `string`            | The email address of the requester.                                         |
| `secret`         | `string`            | The shared secret key for authentication.                                   |
| `task`           | `string`            | A short identifier for the task (e.g., "portfolio-page").                   |
| `round`          | `integer`           | The processing round. `1` for initial creation, `2` for revision.           |
| `nonce`          | `string`            | A unique string to identify this specific job run.                          |
| `brief`          | `string`            | A detailed description of the app to be built or the changes to be made.    |
| `checks`         | `List[string]`      | A list of requirements or checks the final code must satisfy.               |
| `evaluation_url` | `string`            | The URL to which the final repository details will be posted.               |
| `attachments`    | `List[Attachment]`  | (Optional) A list of file attachments provided as data URIs.                |

### `Attachment` Object

| Field  | Type     | Description                                     |
| ------ | -------- | ----------------------------------------------- |
| `name` | `string` | The name of the attached file (e.g., "logo.svg"). |
| `url`  | `string` | The content of the file encoded as a data URI.  |

### Example Request

```json
{
  "email": "user@example.com",
  "secret": "your_strong_secret_key",
  "task": "simple-calculator",
  "round": 1,
  "nonce": "a1b2c3d4e5",
  "brief": "Create a simple calculator with basic arithmetic operations (add, subtract, multiply, divide). The calculator should have a clean, modern interface.",
  "checks": [
    "All four basic operations must be functional.",
    "The display should update correctly after each operation.",
    "There should be a clear (C) button."
  ],
  "evaluation_url": "https://example.com/api/evaluate",
  "attachments": []
}
```

### Success Response

If the request is valid and authenticated, the server will immediately respond with a confirmation message. The actual processing happens in the background.

```json
{
  "status": "success",
  "task": "simple-calculator",
  "round": 1,
  "message": "Your request is being processed in the background."
}
```

### Error Responses

  - **401 Unauthorized**: If the provided `secret` key is invalid.
  - **400 Bad Request**: If the request payload fails Pydantic validation (e.g., missing fields, incorrect data types).
