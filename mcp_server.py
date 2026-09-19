import json
import sys
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import tool

from lead_models import CustomerLead
from lead_db import get_lead_db

# Initialize MCP Server (MCP 2.x SDK)
try:
    from mcp.server.mcpserver import MCPServer
    mcp_server = MCPServer(name="InsureX-Lead-Collector")
except ImportError:
    mcp_server = None

db = get_lead_db()

# --- MCP Native Tools ---

def record_lead_internal(
    session_id: str,
    name: str,
    occupation: str,
    income: str,
    phone_number: str,
    product_interest: str = "ทั่วไป",
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """
    Core business logic: Validates and saves lead into SQLite.
    Returns structured JSON result.
    """
    lead = CustomerLead(
        name=name,
        occupation=occupation,
        income=income,
        phone_number=phone_number,
        product_interest=product_interest,
        notes=notes
    )
    
    if not lead.is_complete:
        missing = lead.get_missing_fields_th()
        return {
            "status": "error",
            "message": f"ข้อมูลยังไม่ครบถ้วน ขาด: {', '.join(missing)}",
            "missing_fields": missing,
            "data": lead.model_dump()
        }
        
    lead_id = db.save_lead(lead, session_id=session_id)
    return {
        "status": "success",
        "message": "บันทึกข้อมูลลูกค้าผู้มุ่งหวังลงในฐานข้อมูล SQLite สำเร็จ",
        "lead_id": lead_id,
        "data": lead.model_dump()
    }

if mcp_server:
    @mcp_server.tool()
    def save_customer_lead_mcp(
        session_id: str,
        name: str,
        occupation: str,
        income: str,
        phone_number: str,
        product_interest: str = "ทั่วไป",
        notes: str = ""
    ) -> str:
        """
        MCP Tool: Record structured customer lead into SQLite database.
        Requires name, occupation, income, and phone number.
        """
        res = record_lead_internal(
            session_id=session_id,
            name=name,
            occupation=occupation,
            income=income,
            phone_number=phone_number,
            product_interest=product_interest,
            notes=notes
        )
        return json.dumps(res, ensure_ascii=False)

    @mcp_server.tool()
    def get_customer_lead_mcp(session_id: str) -> str:
        """
        MCP Tool: Retrieve lead details by session ID.
        """
        lead = db.get_lead_by_session(session_id)
        if lead:
            return json.dumps({"status": "found", "lead": lead}, ensure_ascii=False)
        return json.dumps({"status": "not_found", "message": f"No lead found for session {session_id}"})


# --- LangChain Tool Adapter for LangGraph Workflow ---

class SaveLeadInput(BaseModel):
    session_id: str = Field(description="รหัสประจำตัวเซสชันการสนทนาของผู้ใช้ (Session ID / Thread ID)")
    name: str = Field(description="ชื่อ-นามสกุล ของลูกค้า")
    occupation: str = Field(description="อาชีพของลูกค้า เช่น พนักงานประจำ, เจ้าของกิจการ, ฟรีแลนซ์")
    income: str = Field(description="รายได้ต่อเดือนของลูกค้า เช่น 40,000 บาท")
    phone_number: str = Field(description="เบอร์โทรศัพท์ติดต่อของลูกค้า เช่น 0812345678")
    product_interest: str = Field(default="ทั่วไป", description="ผลิตภัณฑ์ประกันภัยที่ลูกค้าสนใจ เช่น ประกันชีวิต FWD")
    notes: Optional[str] = Field(default=None, description="หมายเหตุเพิ่มเติม เช่น ช่วงเวลาที่สะดวกให้ติดต่อกลับ")

@tool("save_customer_lead_tool", args_schema=SaveLeadInput)
def save_customer_lead_tool(
    session_id: str,
    name: str,
    occupation: str,
    income: str,
    phone_number: str,
    product_interest: str = "ทั่วไป",
    notes: Optional[str] = None
) -> str:
    """
    บันทึกข้อมูลลูกค้าผู้มุ่งหวัง (Lead Collection) ลงในฐานข้อมูล SQLite
    ใช้เมื่อลูกค้าแสดงความสนใจผลิตภัณฑ์ประกัน และให้ข้อมูลครบ 4 อย่าง: ชื่อ, อาชีพ, รายได้, เบอร์ติดต่อ
    """
    res = record_lead_internal(
        session_id=session_id,
        name=name,
        occupation=occupation,
        income=income,
        phone_number=phone_number,
        product_interest=product_interest,
        notes=notes
    )
    return json.dumps(res, ensure_ascii=False)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--stdio":
        print("[MCP Server] Starting InsureX Lead Service over stdio...", file=sys.stderr)
        mcp_server.run()
    else:
        # Self-test tool directly
        print("Testing LangChain tool invocation:")
        result = save_customer_lead_tool.invoke({
            "session_id": "cli_session_999",
            "name": "วิภาดา รักดี",
            "occupation": "ผู้จัดการฝ่ายการตลาด",
            "income": "90,000 บาท/เดือน",
            "phone_number": "086-765-4321",
            "product_interest": "ประกันชีวิต FWD รับสิทธิพิเศษ",
            "notes": "สนใจผ่อน 0% 10 เดือน"
        })
        print("Tool Output:", result)
