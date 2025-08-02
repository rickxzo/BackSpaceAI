# ENV IMPORTS
from ast import Pass
from hmac import new
from dotenv import load_dotenv
import os
load_dotenv()
import tempfile
from parser import code_parser
import random

# BACKEND IMPORTS
import json
from flask import Flask, render_template, jsonify, request
import requests

# AGENT IMPORTS
from typing import TypedDict, List, Dict
from langgraph.graph import START, END, StateGraph

# WEB SEARCH IMPORTS
from exa_py import Exa
exa_api = os.getenv("EXA_API_KEY")
exa = Exa(api_key = exa_api)
from openai import OpenAI
client = OpenAI(
    base_url = "https://api.exa.ai",
    api_key = exa_api,
)

# SANDBOX IMPORTS
from daytona import Daytona, DaytonaConfig
config = DaytonaConfig(api_key=os.getenv("DAYTONA_API_KEY"))
daytona = Daytona(config)

# LLM INFERENCE IMPORTS
import replicate
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
replicate.Client(REPLICATE_API_TOKEN=REPLICATE_API_TOKEN)



# STTModel
class STTModel:
    def __init__(self):
        self.model_name = "openai/gpt-4o-mini-transcribe"
    def run(self, audio_file):
        output = replicate.run(
            self.model_name,
            input={
                #"task": "transcribe",
                "audio_file": audio_file,
                "language": "en",
                #"timestamp": "chunk",
                #"batch_size": 64,
                #"diarise_audio": False,
                "temparature": 0
            }
        )
        x = " ".join(output)
        return x
stt = STTModel()

# T2T Model
class TextAgent:
    def __init__(self, model_name, system_prompt):
        self.model_name = model_name
        self.system_prompt = system_prompt
    def gen(self, prompt):
        input = {
            "prompt": prompt,
            "system_prompt": self.system_prompt,
        }
        x = ''
        for event in replicate.stream(
            self.model_name,
            input=input
        ):
            x += str(event)
        return x
    
Filer = TextAgent(
    "openai/o4-mini",
    """
    You are a code analyzer and documenter.
    Given the code for a file, you are to describe in words what the code in the file does.
    Make sure you do not miss out any details.
    Ex: For a flask app, understand the code and explain the overall file and each function.
    Keep it as short as possible, preferable point wise.
    @ OUTPUT FORMAT
    {
        "type": "file-type",
        "content": "file-description"
    }
    """
)

PyCoder = TextAgent(
    "openai/gpt-4.1",
    """
    @ ROLE
    You are a python coding agent, managed by a manager.
    Provided a file code and change instructions, rewrite the code.

    @ INPUTS
    -> Old Code
    -> Change Required
    
    @ INSRUCTIONS
    -> Always understand the file content properly.
    -> Write the final code, which would be the entire original code with your edits. Do not leave out any part even if the managers asks so. [STRICT]
    -> If instruction feels ambiguous or provided code seems irrelevant, send back a relevant query to the manager.

    @ OUTPUT FORMAT
    -> Writing final code
    {
        "type": "code",
        "content": "your-code"
    }
    -> Querying the manager
    {
        "type": "query",
        "content": "your-query"
    }
    """
)

Manager = TextAgent(
    "openai/gpt-4.1",
    """
    @ ROLE
    You are a Project Manager.
    You are provided with a set of files belonging to a github repository, along with a conversation history with the user.
    You are to understand the file contents, project structure and the user's demands, and take reasonable action.
    You are provided with certain tools and assistants to take action.

    @ INPUTS
    -> Project Files.
    -> Conversation History.
    -> Available assistants & tools.

    @ WORK FLOW
    -> Read all files and their contents.
    -> Understand their use and overall project structure.
    -> Understand which files need to be changed given user's demands.
    -> Converse with user to avoid ambiguity.
    -> Draft a step by step plan.
    -> Send change instructions to assistants with file_name step by step.

    @ OUTPUT FORMAT
    ALWAYS PROVIDE OUTPUT IN JSON.
    -> When replying to user:
    {
        "type": "reply",
        "content": "your-reply"
    }
    -> When drafting plan:
    {
        "type": "plan",
        "content": "your-plan"
    }
    -> When sending instructions to assistants:
    {
        "type": "instruct",
        "name": "assistant-name",
        "file": "name-of-file",
        "content": "your-instructions",
    }
    -> When using tool:
    {
        "type": "tool",
        "name": "tool-name",
        "content": "your-query"
    }

    @ NOTE
    You are to accept only projects with a Flask backend and HTML, CSS, JS frontend.
    Tell the user that your incapable of commiting to other stacks.
    Your assistants might send back a query instead of code when underconfident, converse with user/rethink to resolve the issue.
    The files you are provided contain an description of what they do instead of the actual code.
    DO NOT USE "/", "\", "\n" in your response. [STRICT]
    DO NOT CALL "plan" if a plan is already present. [STRICT] 
    USE '' instead of "" when using strings withing your response. [STRICT]

    @ THINK
    Your assistants can only write code. Provide them with unit instructions.
    Example:
    User's demand: Make a dashboard with authentication.
    Your plan: Tell assistant to make a dashboard backend -> Tell assistant to make a dashboard frontend -> Tell assistant to make auth backend -> Tell assistant to make auth frontend.
    Your plans should be divided into small units for it to be easy to implement at each stage.
    Provide instructions the same.
    This example is a sample case, do not do work you dont have an assistant for.

    @ END
    Based on all assistant responses, provide reply to user.
    Your reply may consist of success/failure or changes and downloadable updated file(s) link.
    """
)

def file_describe():
    global Filer
    global repo_files
    desc = """"""
    for i in repo_files.keys():
        out = Filer.gen(repo_files[i])
        print(f"\nDESC FOR {i}: ", out)
        desc += f"""
        FILE: {i}
        DESCRIPTION: {out}
        """
    return desc

file_desc = """
FILE: .gitignore
        DESCRIPTION: {"type":"gitignore","content":"This Git ignore file lists common files and directories to exclude from version control in Python projects. Key sections:n1. Byte-compiled/optimized files: __pycache__/, *.py[cod], *$py.classn2. C extensions: *.son3. Distribution/packaging: build/, dist/, eggs/, *.egg-info/, wheels/, MANIFEST, etc.n4. PyInstaller artifacts: *.spec, *.manifestn5. Installer logs: pip-log.txt, pip-delete-this-directory.txtn6. Test/coverage outputs: .tox/, .nox/, .coverage*, htmlcov/, nosetests.xml, coverage.xml, .pytest_cache/, .hypothesis/n7. Localization files: *.mo, *.potn8. Framework-specific:n   • Django: *.log, local_settings.py, db.sqlite3*n   • Flask: instance/, .webassets-cachen   • Scrapy: .scrapyn   • Sphinx: docs/_build/n9. Build tools: .pybuilder/, target/n10. Notebooks/IPython: .ipynb_checkpoints, profile_default/, ipython_config.pyn11. Version managers/environments: .python-version, .env, .venv, env/, venv/, ENV/, etc.n12. Lock files (optional): Pipfile.lock, poetry.lock, pdm.lock, pixi.lock, uv.lock, __pypackages__/n13. Task runners/Celery: celerybeat-schedule, celerybeat.pidn14. Other caches/debug symbols: .mypy_cache/, .pyre/, .pytype/, cython_debug/, .ruff_cache/n15. IDE/editor settings: .spyderproject, .ropeproject, .vscode/ (optional), JetBrains templatesn16. Tool-specific ignores: .abstra/, .cursorignore, .cursorindexingignore, marimo/ directoriesnnOverall, it prevents committing temporary, build, cache, virtual-env, IDE, and sensitive configuration files in Python projects."}

        FILE: LICENSE
        DESCRIPTION: {"type":"license","content":"This file is the full text of the Apache License, Version 2.0. It establishes the terms under which recipients may use, modify, reproduce, and distribute the licensed work. Key points:n1. Definitions – clarifies terms like “License,” “Work,” “Contribution,” and “Derivative Works.”n2. Copyright Grant – grants a perpetual, worldwide, royalty-free license to reproduce, distribute, and create derivative works.n3. Patent Grant – grants a royalty-free patent license covering contributors’ patented inventions embodied in the work; patent litigation by the licensee terminates this license.n4. Redistribution Conditions – requires preservation of the license text, copyright and patent notices, notices of modification, and any NOTICE file contents.n5. Contributions – any submissions are automatically licensed under Apache 2.0 unless otherwise stated.n6. Trademarks – does not grant rights to use licensors’ trademarks except for attribution.n7. Warranty Disclaimer – provides the work “AS IS,” without warranties.n8. Limitation of Liability – disclaims contributors’ liability for damages arising from use of the work.n9. Option to Offer Warranty – licensees may offer paid support or warranty but assume sole responsibility for any liabilities.nnAn appendix shows how to apply this license to other works."}

        FILE: README.md
        DESCRIPTION: ```json
{
  "type": "README.md",
  "content": "AvenChatbot-v1 is a multi-modal AI assistant built with a Flask backend and Vue.js/TailwindCSS frontend. It handles:n  • Text-to-Text: user prompt → (optional) Pinecone Index search → (optional) Exa.ai web search → Replicate AI inference → responsen  • Audio-to-Text: user audio → STT model → same T2T pipelinen  • Audio-to-Audio: user audio → STT → T2T pipeline → TTS → audio playbacknnKey components:n  • AI Inference: Replicaten  • RAG Knowledge Base: Pineconen  • Web Research & Crawl: Exa.ain  • Prompt engineering for relevant recallnnSetup steps:n  1. Install dependenciesn  2. Obtain API keys (Replicate, Exa.ai, Pinecone) and set as environment variablesn  3. Initialize Pinecone index (index_init.py) and configure crawl targets (index_modify.py)n  4. Prepare voice call intro (kokoro.py) and update URL in /static/chatbot.jsn  5. Always run app.py to launch the Flask servernnFuture improvements include streaming responses, real-time model hooks, tool-context architecture, and performance tuning."
}
```

        FILE: app.py
        DESCRIPTION: ```json
{
  "type": "python",
  "content": "This file implements a Flask-based chatbot service that uses multiple AI tools (Exa, OpenAI, Pinecone, Replicate) to answer user queries in a state-driven loop. Key components:nn1. Imports & Initializationn   • Flask for web server; dotenv to load environment variables.n   • Exa client for research tasks, OpenAI client (hosted on Exa.ai), Pinecone vector DB client, Replicate client for custom models.n   • Load API keys for EXA, PINECONE, REPLICATE.nn2. Search & Generation Utilitiesn   • vector_search(prompt): Queries Pinecone vector index, reranks results, returns top text chunks above a score threshold.n   • web_search(prompt): Creates/polls an Exa research task, then streams an OpenAI-style chat completion for the same prompt.n   • TextModel: Wraps a Replicate text-generation model; streams output, escapes backslashes.n   • STTModel: Uses a Replicate model to transcribe uploaded audio files to English text.nn3. Assistant Setupn   • `Assistant`: An instance of TextModel running “openai/o4-mini” with a system prompt that enforces JSON output, instructs tool usage (vector vs web search), and focuses on Aven financial domain.n   • STT instance for speech-to-text.nn4. State Machine for Chatn   • Defines a TypedDict ProcessState with fields `conversation`, `knowledge`, `response`, `reply`.n   • Action functions:n     – choose(state): Feeds conversation + accumulated knowledge into Assistant.gen(), returns its JSON response.n     – route(state): Parses Assistant response, returns the chosen action type ('answer', 'vector', 'web').n     – go_web(state): Performs web_search on the prompt, appends results to knowledge.n     – go_vector(state): Performs vector_search, appends vector results to knowledge.n     – give_reply(state): Extracts the final reply from Assistant response.n   • Build a StateGraph with START → choose → conditional edges → [go_web/go_vector/give_reply] and loops back until give_reply → END.n   • Compile the graph to a callable pipeline.nn5. Flask Routesn   • GET/POST "/": Renders a front-end HTML chat interface.n   • POST "/respond":n     – Receives JSON `{messages: [{from, text}, …]}`.n     – Joins them into a single conversation string.n     – Invokes the compiled state machine with empty knowledge.n     – Returns `{success: true, message: reply}` in JSON (HTML-escaped newlines).n   • POST "/voice-to-text":n     – Accepts an uploaded audio file, saves to a temp .webm file.n     – Uploads it to tmpfiles.org, retrieves a public URL.n     – Runs STTModel on the URL, returns transcribed text.n   • POST "/kokorofy":n     – Receives a text message payload, calls a Replicate TTS model “jaaari/kokoro-82m”.n     – Returns a JSON with the URL of the generated audio.nn6. Entry Pointn   • If run as main, starts Flask in debug mode."  
}
```

        FILE: chatbot.html
        DESCRIPTION: {"type":"html","content":"- Declares an HTML5 document with UTF-8 charset and responsive viewportn- Sets the page title to “Aven Support” and includes an empty <style> block for future CSSn- Defines a <div id="app"> as the mounting point for a Vue.js application, rendering a custom <chatbot> componentn- Loads Tailwind CSS from CDN for utility-first stylingn- Loads Vue 3 (production build) from CDN to power the frontend logicn- Uses Flask’s url_for Jinja helper to include a local chatbot.js script from the static folder, which likely contains the Vue app and chatbot component logic"}

        FILE: index_init.py
        DESCRIPTION: ```json
{
  "type": "python",
  "content": "This script initializes and configures a Pinecone vector index for a chatbot application:nn1. Imports the Pinecone client and reads the API key from the environment variable `PINECONE_API_KEY`.n2. Instantiates a Pinecone client (`pc`) using the retrieved API key.n3. Sets the target index name to `avenchatbot`.n4. Checks if an index named `avenchatbot` already exists in your Pinecone account:n   - If it does not exist, creates it with the following parameters:n     • name: `avenchatbot`n     • cloud provider: AWSn     • region: `us-east-1`n     • embedding configuration:n       – model: `llama-text-embed-v2`n       – field mapping: maps incoming document field `text` to the index field `chunk_text` (for vector embedding).n5. Finally, retrieves and prints the index’s metadata (status, dimension, pod type, etc.) by calling `pc.describe_index("avenchatbot")`.nnIn summary, this file ensures that a Pinecone vector index named `avenchatbot` is available with a specific embedding model and then outputs its configuration."
}
```

        FILE: index_modify.py
        DESCRIPTION: {"type": "python","content":"This Python script performs the following steps:n1. Loads environment variables from a .env file.n2. Imports and initializes an Exa client (using EXA_API_KEY) and a Pinecone client/index (using PINECONE_API_KEY).n3. Calls Exa.get_contents on the URL list ["aven.com/support"], converts the result to a string, and trims off leading and trailing parts via slicing ([678:-5624]).n4. Defines a regex pattern to match FAQ entries that start with a dash, include a question mark, and reference a down-arrow image link (![down](...)).n5. Finds all pattern matches in the trimmed text and stores their positions.n6. Implements to_ascii_id(), which strips non-ASCII characters and whitespace for safe record IDs.n7. Iterates over each match, extracts the question (ID) and the following answer block by splitting on " ![down]" and trimming fixed offsets.n8. Upserts each FAQ pair into the Pinecone index under the "default" namespace, with fields:n   - _id: ASCII-sanitized question textn   - chunk_text: answer textn   - category: "FAQ"n9. Prints progress (i/total matches) during insertion."}

        FILE: kokoro.py
        DESCRIPTION: ```json
{
  "type": "python",
  "content": "This script uses the Replicate API to convert text to speech.  nn1. Loads environment variables from a .env file via `load_dotenv()`.  n2. Imports necessary modules (`os`, `replicate`).  n3. Retrieves the Replicate API token from the `REPLICATE_API_TOKEN` environment variable.  n4. Defines an `input` dictionary containing:  n   • `text`: the string to be spoken ("Hi! How can I help you?")  n   • `voice`: the voice identifier (`af_bella`).  n5. Calls `replicate.run()` with the model identifier `jaaari/kokoro-82m:f559560eb822dc509045f3921a1921234918b91739db4bf3daab2169b71c7a13` and the `input` dict.  n6. Prints the output URL or data returned by the Replicate model inference."   
}
```

        FILE: requirements.txt
        DESCRIPTION: {
  "type": "requirements.txt",
  "content": "This file lists the Python dependencies needed by the project:nn1. flask         – a micro web framework for building HTTP APIs and web appsn2. python-dotenv – loads environment variables from a .env file into os.environn3. replicate     – client library for running machine-learning models hosted on Replicaten4. pinecone      – SDK for interacting with the Pinecone vector database servicen5. exa_py        – utilities for experiment tracking, data loading, and reproducible workflowsn6. openai        – official OpenAI Python client for calling models like GPT and DALL·E"
}

        FILE: chatbot.js
        DESCRIPTION: {
  "type": "vue-component",
  "content": "This file defines a Vue.js chat-and-call widget named “Support Bot by Aven.” It provides both text chat and voice/call interactions. Key points:nn1. Data Properties:n   • userInput: current text input.n   • rawMessages: full chat history.n   • loading: unused flag for spinner logic.n   • mediaRecorder, audioChunks, recording: manage voice recording state.n   • activeTab: toggles between “Chat” and “Call” views.n   • callStarted, callTimer, callDuration: track call status and elapsed time.nn2. Computed:n   • messages: returns the last 20 messages (unused in template).n   • formattedCallDuration: formats callDuration as MM:SS.nn3. Methods:n   • startCall(): marks callStarted=true, resets timer, plays a sample WAV, updates callDuration every second, and once playback ends it starts voice recording.n   • endCall(): stops call timer and marks callStarted=false.n   • speak(url): plays a given audio URL, then toggles recording when playback ends.n   • sendMessage():n     – Prevents empty input.n     – Pushes user message to rawMessages.n     – Shows a temporary “thinking…” bot message.n     – POSTs non-temp messages to /respond on localhost:5000.n     – On success replaces “thinking…” with the bot’s reply.n     – If in a call, also POSTs the reply to /kokorofy to get TTS URL, then plays it.n     – On error removes temp message and shows error text.n   • toggleRecording():n     – If already recording, stops MediaRecorder, clears silence timer, closes AudioContext.n     – Otherwise, requests microphone access, starts recording into audioChunks, and uses an AnalyserNode to detect silence. After 2s of silence it auto-stops.n     – On recorder stop, packages chunks into a Blob, sends to /voice-to-text via FormData, then sets userInput to returned text and auto-sends if in-call.nn4. Template Structure:n   – A centered card with two tab buttons: Chat and Call.n   – Chat tab:n     • Scrollable area showing rawMessages with right/left alignment and styled bubbles.n     • Input field bound to userInput, Enter key or Send button triggers sendMessage().n     • Mic button toggles voice recording.n   – Call tab:n     • When callStarted=false, shows a “Start Call” icon and button.n     • When active, shows elapsed time, call icon, “End Call” button that calls endCall().nn5. Initialization:n   – Registers the component as <chatbot> and mounts it on #app.nnOverall, the component combines text chat, voice-to-text, text-to-speech, and simulated call timing to create an interactive support bot interface."
}
"""

class Py(TypedDict):
    old_code: str
    old_file: str
    instruct: str
    response: str
    code: str

def py_draft(state: Py):
    prompt = f"""
    ### OLD CODE
    {state["old_code"]}

    ### INSTRUCTION
    {state["instruct"]}
    """
    print("\nPY DRAFT PROMPT: ", prompt)
    return {
        "response": PyCoder.gen(prompt)
    }

def py_route(state: Py) -> str:
    response = state["response"]
    print("\nPY ROUTE: ", response)
    if "code" in response[:20]:
        return "code"
    else:
        return "query"

def py_query(state: Py):
    response = json.loads(state["response"])
    print("\nPY QUERY: ", response["content"])
    return {
        "code": response["content"]
    }

def py_code(state: Py):
    response = json.loads(state["response"])
    code = code_parser(response["content"])
    sandbox.fs.replace_in_files(
        files=[f"/home/daytona/workspace/repo/{state["old_file"]}", code],
        pattern="old_code",
        new_value="new_code"
    )
    
    print("\nPY CODE: ", code)
    return {
        "code": code
    }

py_graph = StateGraph(Py)
py_graph.add_node("py_draft", py_draft)
py_graph.add_node("py_query", py_query)
py_graph.add_node("py_code", py_code)
py_graph.add_edge(START, "py_draft")
py_graph.add_conditional_edges(
    "py_draft",
    py_route,
    {
        "code": "py_code",
        "query": "py_query"
    }
)
py_graph.add_edge("py_code", END)
py_graph.add_edge("py_query", END)
py_coder = py_graph.compile()

class Manage(TypedDict):
    conversation: str
    files: List[str]
    tools: List[str]
    assistants: List[str]
    plan: str
    responses: Dict[str,str]
    output: str 
    status: str

import textwrap

def draft(state: dict):
    prompt = textwrap.dedent(f"""
    @ CONVERSATION HISTORY
    {state.get("conversation", "")}

    @ ASSISTANTS
    {state.get("assistants", "")}

    @ TOOLS
    {state.get("tools", "")}

    @ FILES
    {state.get("files", "")}

    @ PLAN
    {state.get("plan", "")}

    @ ASSISTANT RESPONSES
    {state.get("responses") if state.get("responses") else "No assistant interaction yet."}
    """)
    print("\nMANAGER DRAFT: ", prompt)
    return {
        "output": Manager.gen(prompt)
    }

def route(state: Manage) -> str:
    output = state["output"]
    print("\nSTATE: ", output)
    new_output = json.loads(output)
    return new_output["type"]

def reply(state: Manage):
    output = state["output"]
    new_output = json.loads(output)
    print("\nREPLY: ", new_output["content"])
    return {
        "status": new_output["content"]
    }

def plan(state: Manage):
    output = str(state["output"])
    output = json.loads(output)
    print("\nPLAN: ", output)
    plan = output["content"]
    return {
        "plan": plan
    }

def instruct(state: Manage):
    global repo_files
    output = state["output"]
    print("\nINSTRUCT: ", output)
    output = json.loads(output)
    to = output["name"]
    file = output["file"]
    content = output["content"]
    response = py_coder.invoke({
        "old_code": repo_files[file],
        "old_file": file,
        "instruct": content,
        "response": "",
        "code": ""
    })["code"]
    astn = state["responses"]
    astn[f"To: {to}. Instruction: {content}"] = response
    return {
        "responses": astn
    }
    

def tool(state: Manage):
    output = state["output"]
    print("\nTOOL USE: ", output)
    return {}


manager_graph = StateGraph(Manage)
manager_graph.add_node("draft", draft)
manager_graph.add_node("reply", reply)
manager_graph.add_node("plan", plan)
manager_graph.add_node("instruct", instruct)
manager_graph.add_node("tool", tool)
manager_graph.add_edge(START, "draft")
manager_graph.add_conditional_edges(
    "draft",
    route,
    {
        "reply": "reply",
        "plan": "plan",
        "instruct": "instruct",
        "tool": "tool"
    }
)
manager_graph.add_edge("instruct", "draft")
manager_graph.add_edge("plan", "draft")
manager_graph.add_edge("tool", "draft")
manager_graph.add_edge("reply", END)
manager = manager_graph.compile()




app = Flask(__name__, template_folder=".", static_folder="static")
app.secret_key = "bksp01"
sandbox = None
repo_files = {}

@app.route("/", methods=["GET","POST"])
def home():
    return render_template("index.html")

@app.route("/respond", methods=["GET","POST"])
def respond():
    global file_desc
    data = request.get_json()
    messages = data['messages']
    conversation = "\n".join(f"{msg['from']}: {msg['text']}" for msg in messages)
    reply = manager.invoke({
        "conversation": conversation,
        "files": file_desc,
        "tools": [],
        "assistants": ["PythonCoder"],
        "plan": "",
        "responses": {},
        "output": "",
        "status": ""

    })
    return jsonify({
        "success": True,
        "message": reply["status"],
    })


@app.route("/daytona-clone", methods=["GET","POST"])
def daytona_pull():
    global file_desc
    global sandbox
    data = request.get_json()
    url = data["url"]
    sandbox = daytona.create()
    sandbox.git.clone(
        url=url,
        path="/home/daytona/workspace/repo"
    )
    files = sandbox.fs.list_files("/home/daytona/workspace/repo")
    for file in files:
        if file.name not in [".git", "static", ".gitignore"]:
            file_path = f"/home/daytona/workspace/repo/{file.name}"
            print(file_path, file.name)
            content = sandbox.fs.download_file(file_path)
            with open("local_file.txt", "wb") as f:
                f.write(content)
            repo_files[file.name] = content.decode('utf-8')
            
    files = sandbox.fs.list_files("/home/daytona/workspace/repo/static")
    for file in files:
        if "." in file.name:
            content = sandbox.fs.download_file(f"/home/daytona/workspace/repo/static/{file.name}")
            with open("local_file.txt", "wb") as f:
                f.write(content)
            repo_files[file.name] = content.decode('utf-8')
    #file_desc = file_describe()
            
    return jsonify({"success": True, "message": "Repository cloned."})

@app.route("/daytona-unlock", methods=["GET","POST"])
def daytona_unlock():
    global sandbox
    sandbox.delete()
    return jsonify({'success': True, "message": "Sandbox closed."})

@app.route("/voice-to-text", methods=["GET","POST"])
def voice_to_text():
    if 'audio' not in request.files:
        return jsonify({'error': 'No audio file'}), 400

    audio_file = request.files['audio']
    with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as temp_audio:
        audio_file.save(temp_audio.name)
        audio_path = temp_audio.name

    try:
        with open(audio_path, "rb") as f:
            upload_response = requests.post("https://tmpfiles.org/api/v1/upload", files={"file": f})
        
        upload_data = upload_response.json()
        file_url = upload_data['data']['url']
    except Exception as e:
        return jsonify({'error': 'Upload failed', 'details': str(e)}), 500

    
    try:
        print(file_url[:20]+"dl/"+file_url[20:])
        result = stt.run(file_url[:20]+"dl/"+file_url[20:])  
        print("RESULT: ", result)
        return jsonify({'text': result})
    except Exception as e:
        return jsonify({'error': 'STT failed', 'details': str(e)}), 500
    


if __name__ == "__main__":
    app.run(debug=True)

