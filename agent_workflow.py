import json
import re
from typing import Dict, Any, Literal
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

import config
from agent_state import AgentState
from lead_models import CustomerLead
from lead_db import get_lead_db
from rag_service import get_rag_service
from mcp_server import record_lead_internal
import prompts

def safe_extract_text(content: Any) -> str:
    """Extract string text from diverse response formats (str, list of dicts, etc.)."""
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(item.get("text", ""))
            elif isinstance(item, str):
                parts.append(item)
            else:
                parts.append(str(item))
        return "".join(parts).strip()
    return str(content).strip()

# Initialize LLMs
def get_llm(temperature: float = 0.2):
    return ChatGoogleGenerativeAI(
        model=config.GOOGLE_MODEL,
        google_api_key=config.GOOGLE_API_KEY,
        temperature=temperature
    )

# --- WORKFLOW NODES ---

def route_intent_node(state: AgentState) -> Dict[str, Any]:
    """
    Analyzes the latest user message and conversation context to route the user's intent:
    - rag_inquiry: Questions about insurance policies, coverage, promotions, terms
    - product_interest: Customer expressing interest in buying/applying (Trigger Mode for Lead Collection)
    - lead_info_provided: Customer providing contact/financial details
    - general_chat: Greeting / memory recall / thank you
    - out_of_scope: Questions unrelated to InsureX or insurance
    """
    messages = state.messages
    if not messages:
        return {"customer_intent": "general_chat"}

    last_user_msg = safe_extract_text(messages[-1].content)
    msg_lower = last_user_msg.lower()

    # Check for direct memory recall queries about past conversation
    if any(k in msg_lower for k in ["จำได้ไหม", "ข้อมูลของฉัน", "สรุปข้อมูลของฉัน", "จำชื่อผมได้ไหม", "ผมชื่ออะไร", "ฉันชื่ออะไร"]):
        return {"customer_intent": "general_chat"}

    # Check if user is currently providing lead info in an active collection
    if state.lead_info and not state.lead_info.is_complete:
        has_lead_keywords = any(char.isdigit() for char in last_user_msg) or any(
            w in msg_lower for w in ["ทำงาน", "อาชีพ", "เงินเดือน", "รายได้", "โทร", "ชื่อ", "บาท", "ตำแหน่ง"]
        )
        if has_lead_keywords:
            return {"customer_intent": "lead_info_provided"}

    # Heuristic fast checks for obvious triggers
    if any(k in msg_lower for k in ["สนใจทำ", "สนใจสมัคร", "อยากทำประกัน", "สนใจโปรโมชั่นนี้", "ติดต่อกลับ", "สมัครเลย", "ซื้อประกัน", "สนใจประกัน"]):
        return {"customer_intent": "product_interest"}
    
    if any(k in msg_lower for k in ["สวัสดี", "หวัดดี", "ขอบคุณ"]) and len(msg_lower.strip()) < 15:
        return {"customer_intent": "general_chat"}

    llm = get_llm(temperature=0.0)
    router_prompt = f"""{prompts.ROUTER_SYSTEM_PROMPT}

ข้อความล่าสุดของลูกค้า: "{last_user_msg}"
สถานะการเก็บข้อมูลลูกค้าปัจจุบัน: {state.lead_info.model_dump_json() if state.lead_info else 'ยังไม่มีข้อมูล'}

ตอบกลับเป็น JSON เช่น {{"intent": "rag_inquiry"}} หรือ {{"intent": "product_interest"}} เท่านั้น"""

    try:
        res = llm.invoke([SystemMessage(content=router_prompt)])
        content = safe_extract_text(res.content)
        clean_content = content.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_content)
        intent = data.get("intent", "rag_inquiry")
    except Exception:
        if any(k in msg_lower for k in ["ประกัน", "เบี้ย", "ลดหย่อน", "ผ่อน", "คุ้มครอง", "โปรโมชั่น", "fwd", "อุ่นใจ", "สิทธิพิเศษ", "เงื่อนไข"]):
            intent = "rag_inquiry"
        elif any(k in msg_lower for k in ["สนใจ", "ซื้อ", "สมัคร"]):
            intent = "product_interest"
        else:
            intent = "out_of_scope"

    return {"customer_intent": intent}


def rag_node(state: AgentState) -> Dict[str, Any]:
    """
    Executes RAG retrieval from ChromaDB knowledge base.
    Evaluates similarity score threshold to enforce error handling if no answer exists.
    """
    messages = state.messages
    last_user_msg = safe_extract_text(messages[-1].content) if messages else ""
    
    rag = get_rag_service()
    docs, is_found = rag.search(last_user_msg)

    if not is_found or not docs:
        return {
            "rag_found": False,
            "error_status": "NOT_FOUND",
            "retrieved_context": ""
        }

    formatted_context = rag.format_context(docs)
    return {
        "rag_found": True,
        "error_status": None,
        "retrieved_context": formatted_context
    }


def lead_extractor_node(state: AgentState) -> Dict[str, Any]:
    """
    Extracts structured lead details (Name, Occupation, Income, Phone Number).
    Merges newly extracted data with existing partial lead data.
    """
    llm = get_llm(temperature=0.0)
    structured_llm = llm.with_structured_output(CustomerLead)

    # Build conversation excerpt for extraction
    history_text = "\n".join([f"{m.type}: {safe_extract_text(m.content)}" for m in state.messages[-6:]])

    extract_prompt = f"""{prompts.LEAD_EXTRACTION_PROMPT}

ประวัติการสนทนา:
{history_text}
"""
    try:
        new_lead = structured_llm.invoke(extract_prompt)
    except Exception as e:
        print(f"[LeadExtractor] Extraction error: {e}")
        new_lead = CustomerLead()

    # Merge with existing lead data
    if state.lead_info:
        merged_lead = state.lead_info.merge_with(new_lead)
    else:
        merged_lead = new_lead

    # Preserve or infer product of interest from context
    if not merged_lead.product_interest or merged_lead.product_interest == "ประกันภัยทั่วไป":
        for msg in state.messages:
            txt = safe_extract_text(msg.content).lower()
            if "fwd" in txt or "ประกันชีวิต" in txt:
                merged_lead.product_interest = "ประกันชีวิต FWD"
                break
            elif "อุ่นใจ" in txt or "ไตรมาส 3" in txt:
                merged_lead.product_interest = "ประกันภัยอุ่นใจ ไตรมาส 3"
                break
            elif "free pa" in txt or "อุบัติเหตุฟรี" in txt:
                merged_lead.product_interest = "InsureX Free PA"
                break
            elif "ครู" in txt or "ศึกษาธิการ" in txt:
                merged_lead.product_interest = "สิทธิพิเศษสำหรับครูและบุคลากรทางการศึกษา"
                break
            elif "อสม" in txt or "สาธารณสุข" in txt:
                merged_lead.product_interest = "สิทธิพิเศษสำหรับบุคลากรสาธารณสุขและ อสม."
                break

    return {"lead_info": merged_lead}


def save_lead_tool_node(state: AgentState) -> Dict[str, Any]:
    """
    Saves complete structured lead into SQLite database via MCP / Tool service.
    """
    lead = state.lead_info
    if not lead or not lead.is_complete:
        return {"lead_saved": False}

    res = record_lead_internal(
        session_id=state.session_id,
        name=lead.name or "",
        occupation=lead.occupation or "",
        income=lead.income or "",
        phone_number=lead.phone_number or "",
        product_interest=lead.product_interest or "ทั่วไป",
        notes=lead.notes
    )
    print(f"[LeadSaver] Successfully recorded lead to SQLite for session '{state.session_id}': {res.get('data')}")
    return {"lead_saved": True}


def fallback_node(state: AgentState) -> Dict[str, Any]:
    """
    Error Handling node: handles cases where knowledge base has no answer
    or user query is out of scope.
    """
    if state.error_status == "NOT_FOUND":
        msg = ("ขออภัยครับ จากการตรวจสอบฐานข้อมูลเอกสารกรมธรรม์และโปรโมชั่นของ InsureX ในปัจจุบัน "
               "ไม่พบข้อมูลตรงกับรายละเอียดที่ท่านสอบถามครับ\n\n"
               "ท่านสามารถสอบถามข้อมูลเพิ่มเติมเกี่ยวกับโปรโมชั่นที่มีในระบบ:\n"
               "• โปรโมชั่นประกันชีวิต FWD (เครดิตเงินคืนสูงสุด 5,700 บาท, ผ่อน 0% สูงสุด 10 เดือน)\n"
               "• โปรโมชั่นประกันภัยอุ่นใจ ไตรมาส 3 (ผ่อน 0% สูงสุด 10 เดือน, เครดิตเงินคืนรวมสูงสุด 5,100 บาท)\n"
               "• InsureX Free PA สำหรับลูกค้า FPC Worksite & Non CB (รับฟรีประกันอุบัติเหตุ)\n"
               "• สิทธิพิเศษสำหรับครูและบุคลากรทางการศึกษา ในสังกัดกระทรวงศึกษาธิการ\n"
               "• สิทธิพิเศษสำหรับบุคลากรสาธารณสุขและอาสาสมัครสาธารณสุขประจำหมู่บ้าน (อสม.) ในสังกัดกระทรวงสาธารณสุข\n\n"
               "หรือติดต่อเจ้าหน้าที่ฝ่ายบริการลูกค้า InsureX ได้โดยตรงที่ โทร. 1314 กด 0 (ทุกวัน 9.00 - 19.00 น.) ครับ")
    else:
        msg = ("สวัสดีครับ น้องอินชัวร์ยินดีให้บริการครับ ผมเป็น AI ผู้ช่วยแนะนำผลิตภัณฑ์และโปรโมชั่นประกันภัยของ InsureX "
               "ท่านสามารถสอบถามรายละเอียดความคุ้มครอง สิทธิพิเศษ เครดิตเงินคืน หรือแจ้งให้เจ้าหน้าที่ติดต่อกลับได้เลยครับ")

    return {"final_response": msg}


def response_generator_node(state: AgentState) -> Dict[str, Any]:
    """
    Synthesizes the final conversational response to the user based on the full conversation state,
    maintaining complete conversation memory and context awareness.
    """
    # If fallback node already generated a response and it's an error/out-of-scope, keep it
    if state.final_response and not state.rag_found:
        final_msg = AIMessage(content=state.final_response)
        return {"messages": [final_msg]}

    llm = get_llm(temperature=0.3)
    system_prompt = prompts.RESPONSE_SYNTHESIS_PROMPT
    last_user_msg = safe_extract_text(state.messages[-1].content) if state.messages else ""

    # Build known lead profile for current session
    lead = state.lead_info
    lead_summary = ""
    if lead and (lead.name or lead.occupation or lead.income or lead.phone_number):
        lead_summary = (
            f"\n[ข้อมูลลูกค้าประจำเซสชันนี้]:\n"
            f"- ชื่อ: {lead.name or 'ยังไม่ระบุ'}\n"
            f"- อาชีพ: {lead.occupation or 'ยังไม่ระบุ'}\n"
            f"- รายได้: {lead.income or 'ยังไม่ระบุ'}\n"
            f"- เบอร์โทร: {lead.phone_number or 'ยังไม่ระบุ'}\n"
            f"- สินค้าที่สนใจ: {lead.product_interest or 'ประกันทั่วไป'}\n"
            f"- สถานะการบันทึกลงฐานข้อมูล: {'บันทึกสำเร็จ' if state.lead_saved else 'ยังไม่ครบถ้วน'}\n"
        )

    # Lead Collection mode responses
    if state.customer_intent in ["product_interest", "lead_info_provided"]:
        if lead and lead.is_complete and state.lead_saved:
            instruction = f"""ลูกค้าให้ข้อมูลครบถ้วนทั้ง 4 อย่างแล้ว และระบบได้บันทึกข้อมูลลงฐานข้อมูล SQLite เรียบร้อย:
{lead_summary}
จงกล่าวขอบคุณลูกค้าอย่างสุภาพ สรุปข้อมูลที่ได้รับ และแจ้งว่าที่ปรึกษาด้านความคุ้มครองของ InsureX จะติดต่อกลับไปตามเบอร์โทรศัพท์ที่แจ้งไว้โดยเร็วที่สุด"""
        else:
            missing = lead.get_missing_fields_th() if lead else ["ชื่อ-นามสกุล", "อาชีพ", "รายได้ต่อเดือน", "เบอร์โทรศัพท์ติดต่อ"]
            instruction = f"""ลูกค้ากำลังอยู่ในขั้นตอนให้ข้อมูลเพื่อปรึกษา/สมัครประกัน
{lead_summary}
ข้อมูลที่ยังขาดอยู่และต้องขอเพิ่ม: {', '.join(missing)}

จงตอบรับความสนใจของลูกค้าอย่างกระตือรือร้น และขอข้อมูลส่วนที่ยังขาดอยู่อย่างสุภาพและเป็นมิตร เพื่อให้เจ้าหน้าที่สามารถประสานงานความคุ้มครองที่ตรงความต้องการที่สุดได้"""

    elif state.customer_intent == "general_chat":
        # General chat or memory recall question
        instruction = f"""คำถามของลูกค้า: "{last_user_msg}"
{lead_summary}
หากลูกค้าถามถึงข้อมูลที่เคยแจ้งไป หรือถามว่าจำได้ไหม ให้ตอบข้อมูลที่ลูกค้าเคยแจ้งไว้อย่างถูกต้อง แม่นยำ และเป็นมิตร"""

    elif state.rag_found and state.retrieved_context:
        instruction = f"""คำถามของลูกค้า: "{last_user_msg}"
{lead_summary}
ข้อมูลจากฐานความรู้ (Knowledge Base):
{state.retrieved_context}

จงตอบคำถามลูกค้าอย่างถูกต้อง ละเอียด ชัดเจน โดยอ้างอิงข้อมูลจากเอกสารข้างต้น และสรุปสิทธิประโยชน์ที่ลูกค้าจะได้รับ"""
    else:
        instruction = f"""คำถามของลูกค้า: "{last_user_msg}"
{lead_summary}
ตอบลูกค้าอย่างสุภาพ แนะนำตัวว่าเป็นผู้ช่วย AI ของ InsureX และเสนอความช่วยเหลือด้านประกันภัย"""

    # Include recent conversation turns for context memory
    recent_messages = []
    if len(state.messages) > 1:
        for m in state.messages[-5:-1]:
            if isinstance(m, HumanMessage):
                recent_messages.append(HumanMessage(content=safe_extract_text(m.content)))
            elif isinstance(m, AIMessage):
                recent_messages.append(AIMessage(content=safe_extract_text(m.content)))

    full_prompt = [
        SystemMessage(content=system_prompt),
        *recent_messages,
        HumanMessage(content=instruction)
    ]

    try:
        res = llm.invoke(full_prompt)
        reply_text = safe_extract_text(res.content)
    except Exception as e:
        reply_text = f"ขออภัยครับ เกิดข้อผิดพลาดในการประมวลผล: {e}"

    ai_msg = AIMessage(content=reply_text)
    return {"messages": [ai_msg], "final_response": reply_text}


# --- CONDITIONAL ROUTING FUNCTIONS ---

def route_after_intent(state: AgentState) -> Literal["rag_node", "lead_extractor_node", "fallback_node", "response_generator_node"]:
    intent = state.customer_intent
    if intent in ["product_interest", "lead_info_provided"]:
        return "lead_extractor_node"
    elif intent == "rag_inquiry":
        return "rag_node"
    elif intent == "general_chat":
        return "response_generator_node"
    else:
        return "fallback_node"

def route_after_rag(state: AgentState) -> Literal["response_generator_node", "fallback_node"]:
    if state.rag_found:
        return "response_generator_node"
    return "fallback_node"

def route_after_lead_extractor(state: AgentState) -> Literal["save_lead_tool_node", "response_generator_node"]:
    if state.lead_info and state.lead_info.is_complete:
        return "save_lead_tool_node"
    return "response_generator_node"


# --- BUILD GRAPH ---

def build_sales_agent_workflow():
    """
    Constructs the LangGraph StateGraph with nodes, edges, cycles,
    and state management checkpointer for session separation.
    """
    workflow = StateGraph(AgentState)

    # Add Nodes
    workflow.add_node("route_intent_node", route_intent_node)
    workflow.add_node("rag_node", rag_node)
    workflow.add_node("lead_extractor_node", lead_extractor_node)
    workflow.add_node("save_lead_tool_node", save_lead_tool_node)
    workflow.add_node("fallback_node", fallback_node)
    workflow.add_node("response_generator_node", response_generator_node)

    # Add Edges
    workflow.add_edge(START, "route_intent_node")

    # Conditional branching from intent router
    workflow.add_conditional_edges(
        "route_intent_node",
        route_after_intent,
        {
            "rag_node": "rag_node",
            "lead_extractor_node": "lead_extractor_node",
            "fallback_node": "fallback_node",
            "response_generator_node": "response_generator_node"
        }
    )

    # Branching after RAG: if found -> response, if not found -> fallback error handling
    workflow.add_conditional_edges(
        "rag_node",
        route_after_rag,
        {
            "response_generator_node": "response_generator_node",
            "fallback_node": "fallback_node"
        }
    )

    # Branching after Lead Extraction: if complete -> save to SQLite tool, else ask for missing fields
    workflow.add_conditional_edges(
        "lead_extractor_node",
        route_after_lead_extractor,
        {
            "save_lead_tool_node": "save_lead_tool_node",
            "response_generator_node": "response_generator_node"
        }
    )

    # Save lead tool routes directly to response synthesis
    workflow.add_edge("save_lead_tool_node", "response_generator_node")

    # Fallback routes to response synthesis
    workflow.add_edge("fallback_node", "response_generator_node")

    # Final response terminates turn
    workflow.add_edge("response_generator_node", END)

    # Compile with MemorySaver checkpointer for session separation
    checkpointer = MemorySaver()
    app = workflow.compile(checkpointer=checkpointer)
    return app

# Singleton compiled agent
_agent_app = None

def get_sales_agent():
    global _agent_app
    if _agent_app is None:
        _agent_app = build_sales_agent_workflow()
    return _agent_app

if __name__ == "__main__":
    agent = get_sales_agent()
    print("LangGraph Sales Agent compiled successfully!")
