# BackSpaceAI
A coding assistant to collaborate with on Github Projects

### What it does?
*Under Development*<br>
BackSpaceAI is a chatbot styled coding assistant, which can collaborate on your github repositories.<br>
Once provided the repository, it clones the entire repository and understands the project file by file.<br>
You can chat with it and provide instructions or ask for guidance, to which the AI Agent will respond appropriately via providing you with explanantions, edited code files etc.<br>
BackSpaceAI currently only supports Flask backend and VueJS / VanillaJS frontend projects.<br>

### Featuress
- Github cloning and code generation<br>
- Audio input<br>
- Web Search<br>
- Sandboxing<br>
- Recall<br>

### Technical Stack
- Flask : Backend
- VueJS : Frontend
- TailwindCSS: Styling
- Web Search: Exa
- Sandboxing: Daytona
- LangGraph: Agent Architecture Design

### Architecture
Provide Github Repo Link --> Repository Sandbox Cloning --> Interact with AI Agent (Manager) --<br>--> Manager uses tools & coding assistants --> Provides response to user

### Future Improvement Scope
- Streaming Response<br>
- Server Sent Events<br>
- Increase Supported Tech Stacks<br>
- Code Testing<br>

#### How to use?
- Install dependencies<br>
- Get API keys from Replicate, Exa.AI, Daytona<br>
- Set API keys as env variables<br>
- Run app.py<br>

This project was made as a part of HeadStarted BuildCore Beta program


