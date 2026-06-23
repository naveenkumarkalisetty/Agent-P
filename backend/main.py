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


class PastJob(BaseModel):
    company: Optional[str] = Field(None, description="Company name")
    title: Optional[str] = Field(None, description="Job title or role at that company")

class CandidateProfile(BaseModel):
    # Basic Info
    first_name: Optional[str] = Field(None, description="Candidate's legal first name")
    last_name: Optional[str] = Field(None, description="Candidate's legal last name")
    email: Optional[str] = Field(None, description="Primary email address")
    phone: Optional[str] = Field(None, description="Phone number including country code if available")

    # Links
    linkedin: Optional[str] = Field(None, description="Full LinkedIn profile URL")
    github: Optional[str] = Field(None, description="Full GitHub profile URL")
    personal_website: Optional[str] = Field(None, description="Personal website or portfolio URL")

    # Current Employment
    current_company: Optional[str] = Field(None, description="Current employer, if any. Return None if a student.")
    current_title: Optional[str] = Field(None, description="Current job title. Return None if a student.")

    # Past Employment (up to 2)
    past_jobs: Optional[list[PastJob]] = Field(None, description="List of up to 2 most recent past jobs (not including the current one). Each with company and title.")

    # Education
    school: Optional[str] = Field(None, description="Most recent university or college name")
    degree: Optional[str] = Field(None, description="Degree type, e.g. Bachelor's, Master's, PhD")
    discipline: Optional[str] = Field(None, description="Field of study or major, e.g. Computer Science")
    edu_start_year: Optional[str] = Field(None, description="Education start year, e.g. 2023")
    edu_end_year: Optional[str] = Field(None, description="Education end year or expected graduation year, e.g. 2027")

    # Skills & Projects
    skills: Optional[list[str]] = Field(None, description="List of technical skills, programming languages, frameworks, and engineering domains mentioned in the resume")
    projects_summary: Optional[str] = Field(None, description="A brief summary of 2-3 notable projects from the resume. Keep each project to one sentence.")

    # Other
    visa_sponsorship: Optional[str] = Field(None, description="Whether the candidate requires visa sponsorship. Only extract if explicitly stated. Return None if not mentioned.")

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
        
        # Use the OS's secure temporary directory for deployment safety
        import tempfile, uuid
        temp_dir = tempfile.gettempdir()
        
        # Create a unique filename so concurrent users don't overwrite each other's resumes
        resume_path = os.path.join(temp_dir, f"resume_{uuid.uuid4().hex[:8]}.pdf")
        
        with open(resume_path, "wb") as f:
            f.write(pdf_content)
            
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
        # print("parsed data:", parsed_profile)
        
        initial_state = {
            "profile": parsed_profile.model_dump(),
            "execution_queue": form_fields,
            "current_index": 0,
            "status": "planning",
            "resume_path": resume_path
        }
        # print("extracted_data:", form_fields)
        new_state = await agent_graph.ainvoke(initial_state, CONFIG)
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

            agent_graph.update_state(CONFIG, {"status": "running"})
                
            new_state = await agent_graph.ainvoke(None, CONFIG)
                
            last_index = new_state.get('last_updated_index', -1)
            queue = new_state.get('execution_queue', [])
            
            updated_field = None
            if last_index >= 0 and last_index < len(queue):
                updated_field = queue[last_index]
                # If it's a dirty field being fixed, use its actual index for the frontend
                payload = {
                    "type": "FIELD_UPDATED",
                    "field": updated_field,
                    "currentIndex": last_index + 1,
                    "liveImage": await browser_manager.get_screenshot_b64(),
                    "was_modified": updated_field.get('status') == 'completed' and 'current_index' not in new_state # Heuristic or we can just let frontend handle text
                }
                
                yield f"data: {json.dumps(payload)}\n\n"
                
            if updated_field and updated_field.get('status') == 'completed':
                await asyncio.sleep(0.7) # Pause to let the user see the typing
            else:
                await asyncio.sleep(0.2)

    except asyncio.CancelledError:
        print("Client disconnected (AbortSignal). Halting the graph safely.")
        agent_graph.update_state(CONFIG, {"status": "paused"})
        raise

@app.get('/api/stream-execution')
async def stream_execution():
    return StreamingResponse(event_generator(), media_type="text/event-stream")

from typing import List

class ChatInstruction(BaseModel):
    message: str

class FieldUpdate(BaseModel):
    id: str = Field(description="The exact ID of the field to update (e.g., 'element_3')")
    new_value: str = Field(description="The new value to set for this field. For checkboxes, use 'check' or 'uncheck'. To skip/clear, use empty string.")

class ChatInstructionUpdates(BaseModel):
    updates: List[FieldUpdate] = Field(description="List of fields to update based on the instruction")

chat_parser = PydanticOutputParser(pydantic_object=ChatInstructionUpdates)

chat_prompt = PromptTemplate.from_template(
    """You are an intelligent assistant helping to update form fields based on a user's natural language instruction.
    
    Current Form Fields:
    {queue}
    
    User Instruction: "{instruction}"
    
    Analyze the user's intent and determine if any form fields need to be updated.
    
    RULES:
    1. If the user tells you to change a field's value, return the exact field 'id' and the 'new_value'.
    2. If the user tells you to skip, clear, or leave a field blank, set the 'new_value' to "".
    3. If the user tells you to "fill this field again", "retry", or click a field using the value you already have, return the field 'id' and set the 'new_value' to its CURRENT value from the list above.
    4. If the user just says "continue", "my bad", "go ahead", or indicates that NO changes are needed, you MUST return an empty array for updates: {{"updates": []}}.
    
    IMPORTANT: You MUST return the result in this EXACT JSON format, wrapped in the "updates" array:
    {{"updates": [{{"id": "element_X", "new_value": "some value"}}]}}
    
    {format_instructions}
    """
)
chat_chain = chat_prompt.partial(format_instructions=chat_parser.get_format_instructions()) | llm | chat_parser

@app.post("/api/chat-instruction")
async def handle_chat(instruction: ChatInstruction):
    print(f"Chat Instruction received: {instruction.message}")
    
    current_state = agent_graph.get_state(CONFIG).values
    queue = current_state.get("execution_queue", [])
    
    # Format queue context to save tokens (we only need id, label, and current value)
    queue_context = json.dumps([{"id": f["id"], "label": f["label"], "current_value": f["value"]} for f in queue])
    
    try:
        result = await chat_chain.ainvoke({
            "queue": queue_context,
            "instruction": instruction.message
        })
        
        # Apply updates back to the queue
        updates_map = {u.id: u.new_value for u in result.updates}
        updated_fields = []
        for field in queue:
            if field["id"] in updates_map:
                field["value"] = updates_map[field["id"]]
                field["status"] = "dirty"
                updated_fields.append({"label": field["label"], "value": field["value"]})
                print(f"Chat updated field [{field['label']}] to '{field['value']}'")
                
        agent_graph.update_state(CONFIG, {"execution_queue": queue})
        return {"status": "success", "updated_fields": updated_fields}
    except Exception as e:
        print(f"Failed to process chat instruction: {e}")
    
    return {"status": "success", "updated_fields": []}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False, loop="asyncio")