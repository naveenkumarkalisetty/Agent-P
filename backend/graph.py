from browser import browser_manager
from langchain_core.output_parsers import format_instructions
from typing import List, Dict, Any, Literal, TypedDict
from langgraph.graph import StateGraph, START, END
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import os
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langgraph.checkpoint.memory import MemorySaver
load_dotenv()

# chatstate
class AgentState(TypedDict):
    profile: Dict[str, Any] # resume fields
    execution_queue: List[Dict[str, Any]] # form fields from playwright
    current_index: int
    status: Literal["planning", "running", "paused", "completed"]

class FieldMapping(BaseModel):
    id:str = Field(description="The exact element ID from the execution queue, e.g., element_0")
    value: str = Field(description="The mapped value from the candidate profile")

class FillPlan(BaseModel):
    mappings: List[FieldMapping]


async def planner_node(state: AgentState) -> Dict[str, Any]:
    """
    Looks at the empty form fields and the candidate profile,
    and generates a plan of what values to type into which fields.
    """
    print("Planner Node: Mapping candidate profile to form fields...")

    profile = state["profile"]
    queue = state['execution_queue']

    # llm initialization
    llm = ChatGroq(
        model="llama-3.3-70b-versatile", 
        temperature=0,
        api_key=os.environ.get("GROQ_API_KEY")
    )
    parser = PydanticOutputParser(pydantic_object=FillPlan)
    prompt = PromptTemplate.from_template(
        """You are an intelligent form-filling agent. 
        Match the candidate's profile data to the provided web form fields.
        Only create mappings for fields where you have matching data. Leave the rest alone.
        
        CANDIDATE PROFILE:
        {profile}
        
        AVAILABLE FORM FIELDS:
        {fields}
        
        Return the response in json format
        {format_instructions}
        """
    )
    chain = prompt.partial(format_instructions=parser.get_format_instructions()) | llm | parser
    
    plan:FillPlan = await chain.ainvoke({
        "profile": str(profile),
        "fields": str([{ 'id': f['id'], 'label': f['label'], 'type': f['type'] }  for f in queue])
    })
    
    # update execution queue
    updated_queue = list(queue) # old queue
    for mapping in plan.mappings:
        for field in updated_queue:
            if field['id'] == mapping.id:
                field['value'] = mapping.value
                break
    print(f"Planner Node: Successfully mapped {len(plan.mappings)} fields.")

    return {
        "execution_queue": updated_queue,
        "status": "running"
    }

async def executor_node(state: AgentState) -> Dict[str, Any]:
    """
    Executes the next pending field in the queue.
    """
    queue = state["execution_queue"]
    idx = state["current_index"]
    
    # user's customization of fields before execution
    for i, field in enumerate(queue):
        if field.get('status') == 'dirty':
            print(f"Fixing modified field: {field['label']} -> {field['value']}")
            
            # playwright fill logic
            if browser_manager.page:
                try:
                    await browser_manager.page.locator(field['selector']).clear()
                    await browser_manager.page.fill(field['selector'], field['value'])
                except Exception as e:
                    print(f"Playwright correction failed: {e}")
            
            queue[i]['status'] = 'completed'
            return { 'execution_queue': queue }
    
    if idx < len(queue):
        current_field = queue[idx]
        
        if current_field.get('value') and current_field.get('status') == 'queued':
            print(f"Typing into field [{current_field['label']}]: {current_field['value']}")
            # playwright fill logic here
            if browser_manager.page:
                try:
                    if current_field['type'] == 'select':
                        await browser_manager.page.select_option(current_field['selector'], label=current_field['value'])
                    else:
                        await browser_manager.page.fill(current_field['selector'], current_field['value'])
                except Exception as e:
                    print(f"Playwright execution failed for {current_field['label']}: {e}")
                    
            queue[idx]['status'] = 'completed'
            return {
                'execution_queue': queue,
                'current_index': idx + 1
            }
    return { 'status': 'completed'}

def router_logic(state: AgentState) -> str:
    """
    Decides whether to keep looping, pause for human input, or finish
    """
    
    if state['status'] == 'paused':
        return "pause_interrupt"
    
    if state['status'] == 'completed' or state['current_index'] >= len(state['execution_queue']):
        return "end"
    
    return "continue"

graph = StateGraph(AgentState)

graph.add_node("planner", planner_node)
graph.add_node("executor", executor_node)

graph.add_edge(START, "planner")
graph.add_edge("planner", "executor")

graph.add_conditional_edges(
    "executor",
    router_logic,
    {
        "continue": "executor",
        "pause_interrupt": END,
        "end": END
    }
)

memory = MemorySaver()
agent_graph = graph.compile(checkpointer=memory, interrupt_before=['executor'])