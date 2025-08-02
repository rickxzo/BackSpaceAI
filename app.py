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
        x = x.replace('\\', '\\\\')
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
    -> Your previous code (if any)
    -> Your previous code's output (if any)
    
    @ INSRUCTIONS
    -> Always understand the file content properly.
    -> Always write test code first (with print output to fetch output)
    -> Write the final code if your test code's output matches the expected output.
    -> If instruction feels ambiguous or provided code seems irrelevant, send back a relevant query to the manager.

    @ OUTPUT FORMAT
    -> Writing test code
    {
        "type": "test",
        "content": "your-code"
    }
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

file_desc = ""

class Py(TypedDict):
    old_code: str
    instruct: str
    test_code: str
    output: str
    code: str
    response: str

def py_draft(state: Py):
    prompt = f"""
    ### OLD CODE
    {state["old_code"]}

    ### INSTRUCTION
    {state["instruct"]}

    ### TEST CODE
    {state["test_code"]}

    ### TEST CODE OUTPUT
    {state["output"]}
    """
    print("\nPY DRAFT PROMPT: ", prompt)
    return {
        "response": PyCoder.gen(prompt)
    }

def py_route(state: Py) -> str:
    response = json.loads(state["response"])
    print("\nPY ROUTE: ", response["type"])
    return response["type"]

def py_query(state: Py):
    response = json.loads(state["response"])
    print("\nPY QUERY: ", response["content"])
    return {
        "code": response["content"]
    }

def py_test(state: Py):
    response = json.loads(state["response"])
    code = code_parser(response["content"])
    output = sandbox.process.code_run(code)
    print("\nPY TEST CODE: ", code)
    print("\nPY TEST OUT: ", output)
    return {
        "test_code": code,
        "output": output
    }

def py_code(state: Py):
    response = json.loads(state["response"])
    print("\nPY CODE: ", code_parser(response["content"]))
    return {
        "code": code_parser(response["content"])
    }

py_graph = StateGraph(Py)
py_graph.add_node("py_draft", py_draft)
py_graph.add_node("py_query", py_query)
py_graph.add_node("py_test", py_test)
py_graph.add_node("py_code", py_code)
py_graph.add_edge(START, "py_draft")
py_graph.add_conditional_edges(
    "py_draft",
    py_route,
    {
        "test":"py_test",
        "code": "py_code",
        "query": "py_query"
    }
)
py_graph.add_edge("py_test", "py_draft")
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
    global files
    output = state["output"]
    print("\nINSTRUCT: ", output)
    to = output["name"]
    file = output["file"]
    content = output["content"]
    response = py_coder.invoke({
        "old_code": files[file],
        "instruct": content,
        "test_code": "",
        "output": "",
        "code": "",
        "response": ""
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
        if file.name not in [".git", "static"]:
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
    file_desc = file_describe()
            
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

