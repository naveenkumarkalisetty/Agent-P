# Agent-P: Autonomous Browser Pilot

Agent-P is an intelligent, autonomous browser automation tool designed to take over tedious web forms and data entry tasks (like job applications). You provide a URL and a Resume (PDF), and Agent-P will automatically map your profile, navigate the form, and let you watch the magic happen via a live-streamed browser view. 

It features a built-in "Human-in-the-Loop" architecture: you can pause execution at any time, chat with the agent to correct its behavior, and seamlessly resume.

---

## How to Run Locally

### Prerequisites
- Node.js (v18+)
- Python (3.10+)
- A [Groq API Key](https://console.groq.com/keys) for the LLM.

### 1. Backend Setup (FastAPI + LangGraph + Playwright)
1. Navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Create a virtual environment and activate it (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install the required Python packages:
   ```bash
   pip install fastapi uvicorn pydantic langchain-groq langgraph playwright python-multipart python-dotenv pdfplumber
   ```
4. Install the Playwright Chromium browser binaries:
   ```bash
   playwright install chromium
   ```
5. Create a `.env` file in the `backend` directory and add your Groq key:
   ```env
   GROQ_API_KEY=your_api_key_here
   ```
6. Start the backend server:
   ```bash
   python main.py
   ```
   *The server will run on `http://localhost:8000`.*

### 2. Frontend Setup (Next.js + Tailwind)
1. Open a new terminal and navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install the Node modules:
   ```bash
   npm install
   ```
3. Start the development server:
   ```bash
   npm run dev
   ```
4. Open your browser to `http://localhost:3000` and launch the pilot workspace!

---

## Key Decisions & Why

1. **LangGraph for State Management:** 
   I chose to model the agent's logic as a State Graph (Planner Node → Executor Node) rather than a continuous conversational loop. This deterministic architecture allowed me to natively implement the **Human-in-the-Loop** feature. If the user hits "Stop", we safely pause the graph, accept conversational tweaks to the state (modifying the execution queue), and seamlessly resume execution exactly where it left off.
   
2. **Server-Sent Events (SSE):** 
   Instead of using WebSockets, I used SSE (`text/event-stream`) to pipe real-time updates and screenshots from the backend to the frontend. Since the data flow is strictly unidirectional during execution (Backend → Frontend), SSE is lighter, less prone to connection-drop complexities, and handles text/base64 buffering flawlessly.

3. **DOM Parsing over Pure Vision:** 
   The agent extracts the DOM elements (inputs, textareas, selects) and feeds them to the LLM as a JSON structure, rather than sending screenshots to a Vision model for navigation. This makes the LLM processing incredibly fast (under 3 seconds to map a whole form) and heavily reduces token costs.

---

## Tradeoffs

- **Base64 Streaming vs. WebRTC:** To show the "Live Browser View", I opted to take continuous JPEG screenshots in Playwright, encode them to Base64, and send them via SSE. 
  - *Tradeoff:* It limits the framerate to roughly 2-4 FPS and consumes more bandwidth than a video stream. 
  - *Benefit:* It massively simplifies the architecture. There is no need to deploy WebRTC TURN/STUN servers, making the app much easier to run locally and deploy.
- **LLM Context Limits:** By extracting the entire DOM state into text, forms that are exceptionally massive might approach context limits, though Groq's Llama 3 handles typical forms beautifully.

---

## Known Limitations

1. **CAPTCHAs:** The agent cannot natively bypass CAPTCHA or reCAPTCHA challenges. If it hits one, the user must currently intervene manually if the browser is exposed, or the automation will halt.
2. **Highly Custom Dropdowns:** While I've implemented aggressive logic to handle custom `<div>`-based comboboxes, heavily obfuscated React/Vue dropdowns that do not use standard accessibility tags might occasionally be missed or fail to open.
3. **Multi-Page Applications:** Currently, the state loop is optimized for long single-page forms. Automatic complex multi-page navigation (clicking "Next", mapping the new DOM, and continuing) is supported but can struggle if page load times are highly unpredictable.

---

## Working Demo

Check out the full flow of Agent-P in action, including form extraction, live streaming, and the human-in-the-loop pause/resume interaction!

[**Watch the Walkthrough Video Here**](#) *(Placeholder for Video Link)*

---

## What I'd Do With More Time

If I had more time to expand Agent-P, I would focus on:
1. **Fallback Vision-Language Models (VLM):** I'd implement a fallback node where if the standard DOM-querying fails to interact with a heavily obfuscated element, it takes a screenshot and uses a Vision model (like GPT-4o or Claude 3.5 Sonnet) to determine exactly X/Y coordinates to click.
2. **Dockerized Deployment:** Playwright requires very specific OS-level dependencies (like X11 libs). I'd write a robust `Dockerfile` and `docker-compose.yml` to spin up the frontend, backend, and browser dependencies in an isolated container network.
3. **Persistent Profiles:** I'd add a database (like PostgreSQL or Supabase) so users can save their resume parsing results permanently. Then, they could trigger jobs via a single click or even a Chrome Extension without re-uploading PDFs every time.
