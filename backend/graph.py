from browser import browser_manager
from langchain_core.output_parsers import format_instructions
from typing import List, Dict, Any, Literal, TypedDict
from langgraph.graph import StateGraph, START, END
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import os, asyncio
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langgraph.checkpoint.memory import MemorySaver
load_dotenv()

# chatstate
class AgentState(TypedDict):
    profile: Dict[str, Any] # resume fields
    execution_queue: List[Dict[str, Any]] # form fields from playwright
    current_index: int
    last_updated_index: int
    status: Literal["planning", "running", "paused", "completed"]
    resume_path: str

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
        api_key=os.environ.get("GROQ_API_KEY"),
        model_kwargs={"response_format": {"type": "json_object"}}
    )
    parser = PydanticOutputParser(pydantic_object=FillPlan)
    prompt = PromptTemplate.from_template(
        """You are an intelligent form-filling agent. 
        Match the candidate's profile data to the provided web form fields.
        Only create mappings for fields where you have CONFIDENT matching data. Leave the rest alone.
        
        RULES FOR EACH FIELD TYPE:
        - type "text" or "textarea": set value to the matching text from the profile.
        - type "select" or "combobox": set value to the best matching text from the profile. The agent will type it and pick from the dropdown. Use short, commonly used terms (e.g. "Computer Science" not "Computer Science Engineering").
        - type "checkbox": set value to "check" ONLY if the candidate's skills/profile clearly match the checkbox label. Do NOT check boxes you are unsure about.
        - type "file": set value to "UPLOAD_RESUME" ONLY if the field label is for a Resume or CV. Otherwise, do not map it.
        
        IMPORTANT: NEVER fill EEO fields (gender, race, ethnicity, veteran status, disability status, Hispanic/Latino). Leave them unmapped.
        NEVER fill CAPTCHA or recaptcha fields. Leave them unmapped.
        
        CANDIDATE PROFILE:
        {profile}
        
        AVAILABLE FORM FIELDS:
        {fields}
        
        CRITICAL INSTRUCTION: Return ONLY a raw, valid JSON object. 
        Do NOT write Python code. 
        Do NOT include markdown formatting like ```json. 
        Do NOT include any conversational text or explanations.
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
    print(updated_queue)
    return {
        "execution_queue": updated_queue,
        "status": "running"
    }

async def handle_combobox_select(page, selector: str, value: str, safe_selector: str):
    """
    Handles combobox/autocomplete select fields (like Greenhouse's School, Degree, Discipline).
    Strategy: click → type to filter → poll until dropdown options appear → click best match.
    """
    locator = page.locator(safe_selector)

    # Step 1: Click to focus/open the dropdown
    await locator.click(timeout=2000)
    await asyncio.sleep(0.3)

    # Step 2: Clear any existing value and type character by character
    # Using type() instead of fill() because fill() sets the value instantly
    # and some dropdowns only trigger on keyboard events
    await locator.fill('', timeout=2000)  # Clear first
    await locator.press_sequentially(value, delay=50)  # Type like a human

    # Step 3: Poll for dropdown options to appear (up to 3 seconds)
    option_clicked = 'none'
    for attempt in range(6):  # 6 attempts × 500ms = 3 seconds max
        await asyncio.sleep(0.5)
        
        option_clicked = await page.evaluate(f"""
            (() => {{
                const targetValue = `{value.replace('`', '').replace("'", "\\'")}`.toLowerCase();
                
                // Common dropdown option selectors across job board platforms
                const optionSelectors = [
                    'li[role="option"]',
                    '.select2-results li',
                    '.dropdown-menu li',
                    'ul[role="listbox"] li',
                    'div[class*="option"]',
                    'li[class*="option"]',
                    '.autocomplete-results li',
                    '[class*="dropdown"] li',
                    '[class*="menu"] li[id]'
                ];
                
                for (const optSel of optionSelectors) {{
                    const options = [...document.querySelectorAll(optSel)]
                        .filter(el => el.offsetParent !== null);  // Only visible options
                    if (options.length === 0) continue;
                    
                    // Try exact match first
                    for (const opt of options) {{
                        if (opt.textContent.trim().toLowerCase() === targetValue) {{
                            opt.scrollIntoView({{ block: 'nearest' }});
                            opt.click();
                            return 'exact';
                        }}
                    }}
                    
                    // Try partial match (option contains the typed value or vice versa)
                    for (const opt of options) {{
                        const text = opt.textContent.trim().toLowerCase();
                        if (text.includes(targetValue) || targetValue.includes(text)) {{
                            opt.scrollIntoView({{ block: 'nearest' }});
                            opt.click();
                            return 'partial';
                        }}
                    }}
                    
                    // Fallback: click "Other" if available
                    for (const opt of options) {{
                        if (opt.textContent.trim().toLowerCase() === 'other') {{
                            opt.scrollIntoView({{ block: 'nearest' }});
                            opt.click();
                            return 'other';
                        }}
                    }}
                    
                    // Last resort: click the first visible option
                    if (options.length > 0) {{
                        options[0].scrollIntoView({{ block: 'nearest' }});
                        options[0].click();
                        return 'first';
                    }}
                }}
                
                return 'none';
            }})()
        """)
        
        if option_clicked != 'none':
            break  # Successfully clicked an option, stop polling
    
    print(f"  Combobox result for '{value}': {option_clicked} (attempt {attempt + 1})")
    
    if option_clicked == 'none':
        # No dropdown appeared — try native <select> as fallback
        try:
            await locator.select_option(label=value, timeout=1000)
            print(f"  Fell back to native select_option for '{value}'")
        except Exception:
            print(f"  Could not select any option for '{value}'")


async def executor_node(state: AgentState) -> Dict[str, Any]:
    """
    Executes the next pending field in the queue.
    """
    queue = state["execution_queue"]
    idx = state["current_index"]
    
    def get_safe_selector(selector: str) -> str:
        if selector.startswith('#') and ' ' not in selector:
            return f"id={selector[1:]}"
        return selector

    # user's customization of fields before execution
    for i, field in enumerate(queue):
        if field.get('status') == 'dirty':
            print(f"Fixing modified field: {field['label']} -> {field['value']}")
            
            # playwright fill logic
            if browser_manager.page:
                try:
                    safe_selector = get_safe_selector(field['selector'])
                    locator = browser_manager.page.locator(safe_selector)
                    
                    await browser_manager.page.evaluate(f"""
                        try {{
                            let el = null;
                            let sel = '{field['selector']}';
                            if (sel.startsWith('#') && !sel.includes(' ')) {{
                                el = document.getElementById(sel.substring(1));
                            }} else {{
                                el = document.querySelector(sel);
                            }}
                            if(el) {{
                                el.scrollIntoView({{ behavior: 'instant', block: 'center', inline: 'center' }});
                                el.style.border = '3px solid #10b981';
                                el.style.boxShadow = '0 0 15px #10b981';
                                el.style.transition = 'all 0.3s ease';
                            }}
                        }} catch(e) {{}}
                    """)
                    await locator.scroll_into_view_if_needed(timeout=1000)
                    
                    await locator.clear()
                    await locator.fill(field['value'])
                except Exception as e:
                    print(f"Playwright correction failed: {e}")
            
            queue[i]['status'] = 'completed' if field['value'] else 'ignored'
            return { 'execution_queue': queue, 'last_updated_index': i }
    
    if idx < len(queue):
        current_field = queue[idx]
        
        # Always scroll to the current field to show live progression
        if browser_manager.page:
            safe_selector = get_safe_selector(current_field['selector'])
            locator = browser_manager.page.locator(safe_selector)
            try:
                await browser_manager.page.evaluate(f"""
                    try {{
                        let el = null;
                        let sel = '{current_field['selector']}';
                        if (sel.startsWith('#') && !sel.includes(' ')) {{
                            el = document.getElementById(sel.substring(1));
                        }} else {{
                            el = document.querySelector(sel);
                        }}
                        if(el) {{
                            el.scrollIntoView({{ behavior: 'instant', block: 'center', inline: 'center' }});
                            el.style.border = '3px solid #3b82f6';
                            el.style.boxShadow = '0 0 15px #3b82f6';
                            el.style.transition = 'all 0.3s ease';
                        }}
                    }} catch(e) {{}}
                """)
                await locator.scroll_into_view_if_needed(timeout=1000)
            except Exception as e:
                # Field is likely hidden, which is normal for honeypots or styling
                print(f"Skipped invisible field: {current_field['label']}")

        if current_field.get('value') and current_field.get('status') == 'queued':
            print(f"Typing into field [{current_field['label']}]: {current_field['value']}")
            # playwright fill logic here
            if browser_manager.page:
                safe_selector = get_safe_selector(current_field['selector'])
                locator = browser_manager.page.locator(safe_selector)
                try:
                    await browser_manager.page.evaluate(f"""
                        try {{
                            let el = null;
                            let sel = '{current_field['selector']}';
                            if (sel.startsWith('#') && !sel.includes(' ')) {{
                                el = document.getElementById(sel.substring(1));
                            }} else {{
                                el = document.querySelector(sel);
                            }}
                            if(el) {{
                                el.style.border = '3px solid #10b981';
                                el.style.boxShadow = '0 0 15px #10b981';
                            }}
                        }} catch(e) {{}}
                    """)
                    
                    if current_field['type'] in ('select', 'combobox'):
                        # Use combobox handler for autocomplete/searchable selects
                        print("Select box")
                        await handle_combobox_select(
                            browser_manager.page,
                            current_field['selector'],
                            current_field['value'],
                            safe_selector
                        )
                    elif current_field['type'] == 'checkbox':
                        await locator.check(timeout=2000, force=True)
                        print(f"Checked checkbox [{current_field['label']}]")
                    elif current_field['type'] == 'file':
                        if current_field['value'] == 'UPLOAD_RESUME' and state.get('resume_path'):
                            await locator.set_input_files(state['resume_path'], timeout=3000)
                            print(f"Uploaded resume to [{current_field['label']}]")
                    else:
                        # Check if this is a known autocomplete field by ID pattern
                        sel_lower = current_field['selector'].lower()
                        is_likely_combobox = any(
                            kw in sel_lower for kw in ['school', 'degree', 'discipline', 'location', 'country']
                        )
                        
                        if is_likely_combobox:
                            # Use the full combobox handler for known autocomplete fields
                            print(f"  Detected likely combobox by ID: {current_field['selector']}")
                            await handle_combobox_select(
                                browser_manager.page,
                                current_field['selector'],
                                current_field['value'],
                                safe_selector
                            )
                        else:
                            # Type character-by-character to trigger any autocomplete
                            await locator.click(timeout=2000)
                            await locator.fill('', timeout=2000)
                            await locator.press_sequentially(current_field['value'], delay=60)
                            
                            # Poll for dropdown options (up to 3 attempts × 500ms = 1.5s)
                            dropdown_clicked = False
                            for _attempt in range(3):
                                await asyncio.sleep(0.5)
                                dropdown_clicked = await browser_manager.page.evaluate("""
                                    (() => {
                                        const optionSelectors = [
                                            'li[role="option"]',
                                            'ul[role="listbox"] li',
                                            '.select2-results li',
                                            '.autocomplete-dropdown li',
                                            '[class*="dropdown"] li:not(nav li)',
                                            '[class*="suggestion"]',
                                            '[class*="option"]:not(select option)'
                                        ];
                                        for (const sel of optionSelectors) {
                                            const opts = [...document.querySelectorAll(sel)]
                                                .filter(el => el.offsetParent !== null);
                                            if (opts.length > 0) {
                                                opts[0].scrollIntoView({ block: 'nearest' });
                                                opts[0].click();
                                                return true;
                                            }
                                        }
                                        return false;
                                    })()
                                """)
                                if dropdown_clicked:
                                    break
                            
                            if dropdown_clicked:
                                print(f"  Auto-selected dropdown option for [{current_field['label']}]")
                except Exception as e:
                    print(f"Playwright execution failed for {current_field['label']}: {e}")
                    
            queue[idx]['status'] = 'completed'
        else:
            if browser_manager.page:
                try:
                    await browser_manager.page.evaluate(f"""
                        try {{
                            let el = null;
                            let sel = '{current_field['selector']}';
                            if (sel.startsWith('#') && !sel.includes(' ')) {{
                                el = document.getElementById(sel.substring(1));
                            }} else {{
                                el = document.querySelector(sel);
                            }}
                            if(el) {{
                                el.style.border = '3px solid #ef4444';
                                el.style.boxShadow = '0 0 15px #ef4444';
                            }}
                        }} catch(e) {{}}
                    """)
                except Exception as e:
                    pass
            queue[idx]['status'] = 'ignored'
        return {
            'execution_queue': queue,
            'current_index': idx + 1,
            'last_updated_index': idx
        }
        
    return { 'status': 'completed'}

def router_logic(state: AgentState) -> str:
    """
    Decides whether to keep looping or finish
    """
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
        "end": END
    }
)

memory = MemorySaver()
agent_graph = graph.compile(checkpointer=memory, interrupt_before=['executor'])