import pymupdf4llm
import pymupdf, pymupdf4llm
import asyncio

import sys
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from langchain_groq import ChatGroq
import os
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableConfig
from graph import agent_graph
import uuid, base64,json
from browser import browser_manager
load_dotenv()

THREAD_ID = str(uuid.uuid4())
CONFIG:RunnableConfig = { "configurable": {"thread_id": THREAD_ID}}

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CandidateProfile(BaseModel):
    first_name: Optional[str] = Field(None, description="Candidate's legal first name")
    last_name: Optional[str] = Field(None, description="Candidate's legal last name")
    email: Optional[str] = Field(None, description="Primary email address")
    phone: Optional[str] = Field(None, description="Phone number including country code if available")
    linkedin: Optional[str] = Field(None, description="Full LinkedIn profile URL")
    github: Optional[str] = Field(None, description="Full GitHub profile URL")
    current_company: Optional[str] = Field(None, description="Current employer, if any. Return None if a student.")
    current_title: Optional[str] = Field(None, description="Current job title. Return None if a student.")

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0,
    max_tokens=None,
    timeout=None,
    max_retries=2,
    api_key=os.getenv("GROQ_API_KEY")
)

parser = PydanticOutputParser(pydantic_object=CandidateProfile)

extraction_prompt = PromptTemplate.from_template(
    """You are an expert ATS (Applicant Tracking System) parser. 
    Extract the candidate's core details from the following raw resume text.
    If a specific piece of information is not found in the text, leave it as null. Do not guess or hallucinate.
    
    RAW RESUME TEXT:
    {resume_text}
    You should return in the form of a JSON object
    {format_instructions}
    """
)
extraction_chain = extraction_prompt.partial(format_instructions=parser.get_format_instructions()) | llm | parser

@app.post("/api/initiate-run")
async def initiate_run(resume: UploadFile = File(...), url:str = Form(...)):
    
    if resume.filename and not resume.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF documents are supported.")
    
    try:
        print(f"Received request for URL:{url}")

        pdf_content = await resume.read()
        doc = pymupdf.open(stream=pdf_content, filetype='pdf')
        
        md_text = pymupdf4llm.to_markdown(doc)
        doc.close()
        
        if isinstance(md_text, str) and not md_text.strip():
            raise HTTPException(status_code=400, detail="Could not extract readable text.")
        
        print("Sending markdown text to Groq for structured extraction...")
        
        await browser_manager.start(url)
        parsed_profile_task = extraction_chain.ainvoke({"resume_text": md_text})
        fields_mapping_task = browser_manager.extract_form_fields()
        
        parsed_profile, form_fields = await asyncio.gather(parsed_profile_task, fields_mapping_task)

        # await browser_manager.start(url)
        print("Extraction complete")
        print(parsed_profile)
        
        initial_state = {
            "profile": parsed_profile.model_dump(),
            "execution_queue": form_fields,
            "current_index": 0,
            "status": "planning"
        }
        
        new_state = agent_graph.invoke(initial_state, CONFIG)
        return {
            'status': 'success',
            'execution_queue': new_state['execution_queue'],
            'current_index': new_state['current_index']
        }
        
    except Exception as e:
        print(f"Error parsing resume: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error occurred: {e}")
    
    

async def event_generator():
    try:
        while True:
            current_state = agent_graph.get_state(CONFIG).values

            if current_state.get('status') == 'completed' or current_state.get('current_index', 0) >= len(current_state.get("execution_queue", [])):
                yield f"data: {json.dumps({'type': 'EXECUTION_COMPLETE'})}\n\n"
                break

            current_state['status'] = "running"
            agent_graph.update_state(CONFIG, current_state)
                
            new_state = await agent_graph.ainvoke(None, CONFIG)
                
            current_index = new_state['current_index']
            updated_field = new_state['execution_queue'][current_index - 1]
                
            b64_image = await browser_manager.get_screenshot_b64()

            payload = {
                "type": "FIELD_UPDATED",
                "field": updated_field,
                "currentIndex": current_index,
                "isProcessing": True,
                "liveImage": b64_image  # Sending the visual frame!
            }
                
            yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(1.5)

    except asyncio.CancelledError:
        print("Client disconnected (AbortSignal). Halting the graph safely.")
        current_state = agent_graph.get_state(CONFIG).values
        current_state["status"] = "paused"
        agent_graph.update_state(CONFIG, current_state)
        raise

@app.get('/api/stream-execution')
async def stream_execution():
    return StreamingResponse(event_generator(), media_type="text/event-stream")

class ChatInstruction(BaseModel):
    message: str

@app.post("/api/chat-instruction")
async def handle_chat(instruction: ChatInstruction):
    print(f"Chat Instruction: {instruction.message}")
    
    current_state = agent_graph.get_state(CONFIG).values
    queue = current_state.get("execution_queue", [])
    
    # NLP Matcher (Update to LLM later)
    if "email" in instruction.message.lower():
        for field in queue:
            if field["type"] == "email" or "email" in field["label"].lower():
                new_email = instruction.message.split("to")[-1].strip()
                field["value"] = new_email
                field["status"] = "dirty" 
                break
                
    current_state["execution_queue"] = queue
    agent_graph.update_state(CONFIG, current_state)
    
    return {"status": "success"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False, loop="asyncio")