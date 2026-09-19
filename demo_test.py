import os
import json
import sqlite3
from langchain_core.messages import HumanMessage
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import print as rprint

import config
from agent_workflow import get_sales_agent, safe_extract_text
from lead_db import get_lead_db

console = Console()

def print_separator(title: str):
    console.print(f"\n[bold cyan]{'='*80}[/bold cyan]")
    console.print(f"[bold yellow] >>> {title} <<< [/bold yellow]")
    console.print(f"[bold cyan]{'='*80}[/bold cyan]\n")

def run_test_case_1_rag_precision(agent):
    """
    Test Case 1: RAG Precision
    Demonstrates accurate retrieval from InsureX PDF promotion documents.
    """
    print_separator("TEST CASE 1: RAG PRECISION (KNOWLEDGE BASE RETRIEVAL)")
    
    session_id = "test_eval_rag_precision"
    thread_cfg = {"configurable": {"thread_id": session_id}}
    
    questions = [
        "โปรโมชั่นประกันชีวิต FWD มีเงื่อนไขการผ่อน 0% กี่เดือน และมียอดชำระขั้นต่ำเท่าไหร่?",
        "โปรโมชั่นซื้อความคุ้มครอง ประกันภัย อุ่นใจ ประจำไตรมาส 3 มอบสิทธิพิเศษอะไรสำหรับผู้สมัครบ้าง?",
        "สิทธิพิเศษสำหรับครูและบุคลากรทางการศึกษา ในสังกัดกระทรวงศึกษาธิการ มีเงื่อนไขอายุและจำกัดสิทธิ์อย่างไร?",
        "InsureX Free PA สำหรับลูกค้า FPC Worksite & Non CB ให้ความคุ้มครองเรื่องอะไรบ้าง?"
    ]
    
    for q in questions:
        console.print(f"[bold green]User Query:[/bold green] {q}")
        state_input = {
            "messages": [HumanMessage(content=q)],
            "session_id": session_id
        }
        res = agent.invoke(state_input, config=thread_cfg)
        reply = safe_extract_text(res["messages"][-1].content)
        intent = res.get("customer_intent", "-")
        found = res.get("rag_found", False)
        
        console.print(f"[bold blue]Detected Intent:[/bold blue] {intent} | [bold blue]RAG Found:[/bold blue] {found}")
        console.print(Panel(reply, title="[bold magenta]Sales Agent Response[/bold magenta]", border_style="green"))
        console.print("-" * 60)


def run_test_case_2_error_handling(agent):
    """
    Test Case 2: Error Handling
    Demonstrates handling queries not present in knowledge base or out of scope.
    """
    print_separator("TEST CASE 2: ERROR HANDLING (KNOWLEDGE NOT FOUND / OUT OF SCOPE)")
    
    session_id = "test_eval_error_handling"
    thread_cfg = {"configurable": {"thread_id": session_id}}
    
    out_of_scope_queries = [
        "ข้อสอบถามอัตราเบี้ยประกันภัยยานอวกาศเดินทางไปดาวอังคารหน่อยครับ",
        "ช่วยแนะนำสูตรทำต้มยำกุ้งน้ำข้นให้อร่อยหน่อย"
    ]
    
    for q in out_of_scope_queries:
        console.print(f"[bold green]User Query:[/bold green] {q}")
        state_input = {
            "messages": [HumanMessage(content=q)],
            "session_id": session_id
        }
        res = agent.invoke(state_input, config=thread_cfg)
        reply = safe_extract_text(res["messages"][-1].content)
        intent = res.get("customer_intent", "-")
        found = res.get("rag_found", False)
        error = res.get("error_status", "None")
        
        console.print(f"[bold blue]Detected Intent:[/bold blue] {intent} | [bold blue]RAG Found:[/bold blue] {found} | [bold red]Error Status:[/bold red] {error}")
        console.print(Panel(reply, title="[bold red]Graceful Error Handling Response[/bold red]", border_style="red"))
        console.print("-" * 60)


def run_test_case_3_lead_collection(agent):
    """
    Test Case 3: Bonus Task 1 - Structured Lead Collection (MCP / Tooling)
    Demonstrates mode trigger on product interest, multi-turn collection of Name, Occupation, Income, Phone,
    and structured persistence into SQLite.
    """
    print_separator("TEST CASE 3: BONUS TASK 1 - STRUCTURED LEAD COLLECTION (MCP & SQLITE)")
    
    session_id = "test_eval_lead_collection_001"
    thread_cfg = {"configurable": {"thread_id": session_id}}
    db = get_lead_db()
    db.delete_lead_by_session(session_id)
    
    # Turn 1: Customer triggers interest mode
    turn_1 = "ผมสนใจสมัครโปรโมชั่นประกันชีวิต FWD มากครับ มีเจ้าหน้าที่ติดต่อกลับได้ไหม"
    console.print(f"[bold cyan]Turn 1 - User:[/bold cyan] {turn_1}")
    res1 = agent.invoke({"messages": [HumanMessage(content=turn_1)], "session_id": session_id}, config=thread_cfg)
    reply1 = safe_extract_text(res1["messages"][-1].content)
    console.print(f"[bold blue]State Intent:[/bold blue] {res1.get('customer_intent')} | [bold yellow]Lead Saved:[/bold yellow] {res1.get('lead_saved')}")
    console.print(Panel(reply1, title="[bold magenta]Agent Turn 1 (Requests Missing Lead Fields)[/bold magenta]"))
    
    # Turn 2: Customer provides partial details (Name, Occupation)
    turn_2 = "ผมชื่อ กิตติศักดิ์ พัฒนกิจ ทำงานเป็นผู้จัดการฝ่ายไอทีครับ"
    console.print(f"\n[bold cyan]Turn 2 - User:[/bold cyan] {turn_2}")
    res2 = agent.invoke({"messages": [HumanMessage(content=turn_2)], "session_id": session_id}, config=thread_cfg)
    reply2 = safe_extract_text(res2["messages"][-1].content)
    lead2 = res2.get("lead_info")
    console.print(f"[bold blue]State Intent:[/bold blue] {res2.get('customer_intent')} | [bold yellow]Lead Complete:[/bold yellow] {lead2.is_complete if lead2 else False}")
    console.print(f"[bold blue]Extracted So Far:[/bold blue] Name: {lead2.name}, Job: {lead2.occupation}, Income: {lead2.income}, Phone: {lead2.phone_number}")
    console.print(Panel(reply2, title="[bold magenta]Agent Turn 2 (Requests Remaining Fields)[/bold magenta]"))
    
    # Turn 3: Customer provides remaining details (Income, Phone Number)
    turn_3 = "รายได้ต่อเดือนประมาณ 85,000 บาทครับ เบอร์โทร 081-987-6543 สะดวกติดต่อช่วงบ่ายครับ"
    console.print(f"\n[bold cyan]Turn 3 - User:[/bold cyan] {turn_3}")
    res3 = agent.invoke({"messages": [HumanMessage(content=turn_3)], "session_id": session_id}, config=thread_cfg)
    reply3 = safe_extract_text(res3["messages"][-1].content)
    lead3 = res3.get("lead_info")
    console.print(f"[bold blue]State Intent:[/bold blue] {res3.get('customer_intent')} | [bold green]Lead Complete:[/bold green] {lead3.is_complete if lead3 else False} | [bold green]Lead Saved to DB:[/bold green] {res3.get('lead_saved')}")
    console.print(Panel(reply3, title="[bold green]Agent Turn 3 (Confirms Lead Recorded)[/bold green]"))

    # Verify directly from SQLite DB
    console.print("\n[bold yellow]Direct Database Verification (SQLite 'leads.db'):[/bold yellow]")
    db_record = db.get_lead_by_session(session_id)
    if db_record:
        table = Table(title="Persisted SQLite Record")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="green")
        for k, v in db_record.items():
            table.add_row(str(k), str(v))
        console.print(table)
    else:
        console.print("[bold red]FAILED: No record found in SQLite database![/bold red]")


def run_test_case_4_session_separation(agent):
    """
    Test Case 4: Bonus Task 2 - Advanced Session Management
    Demonstrates conversation memory, session isolation between different customers,
    and context retrieval within each user's thread.
    """
    print_separator("TEST CASE 4: BONUS TASK 2 - ADVANCED SESSION MANAGEMENT (MULTI-USER ISOLATION)")
    
    session_a = "session_user_somchai"
    session_b = "session_user_somying"
    
    db = get_lead_db()
    db.delete_lead_by_session(session_a)
    db.delete_lead_by_session(session_b)
    
    # User A begins conversation
    console.print("[bold cyan]>>> User A (Somchai) Session Started <<<[/bold cyan]")
    msg_a1 = "สวัสดีครับ ผมชื่อ สมชาย มั่งคั่ง ทำงานวิศวกร รายได้ 70,000 บาท สนใจประกันชีวิต FWD เบอร์โทร 081-111-2222 ครับ"
    console.print(f"[bold cyan]User A:[/bold cyan] {msg_a1}")
    res_a1 = agent.invoke({"messages": [HumanMessage(content=msg_a1)], "session_id": session_a}, config={"configurable": {"thread_id": session_a}})
    console.print(Panel(safe_extract_text(res_a1["messages"][-1].content), title="Agent -> User A"))
    
    # User B begins conversation Concurrently
    console.print("\n[bold magenta]>>> User B (Somying) Session Started <<<[/bold magenta]")
    msg_b1 = "สวัสดีค่ะ ฉันชื่อ สมหญิง จริงใจ อาชีพแพทย์ รายได้ 150,000 บาท สนใจประกันภัยอุ่นใจ ไตรมาส 3 เบอร์โทร 089-888-9999 ค่ะ"
    console.print(f"[bold magenta]User B:[/bold magenta] {msg_b1}")
    res_b1 = agent.invoke({"messages": [HumanMessage(content=msg_b1)], "session_id": session_b}, config={"configurable": {"thread_id": session_b}})
    console.print(Panel(safe_extract_text(res_b1["messages"][-1].content), title="Agent -> User B"))
    
    # Memory recall check for User A
    console.print("\n[bold cyan]>>> Memory Recall Check: User A (Somchai) <<<[/bold cyan]")
    msg_a2 = "จำได้ไหมว่าผมชื่ออะไร อาชีพอะไร และผมสนใจประกันตัวไหน?"
    console.print(f"[bold cyan]User A:[/bold cyan] {msg_a2}")
    res_a2 = agent.invoke({"messages": [HumanMessage(content=msg_a2)], "session_id": session_a}, config={"configurable": {"thread_id": session_a}})
    reply_a2 = safe_extract_text(res_a2["messages"][-1].content)
    console.print(Panel(reply_a2, title="Agent Memory Verification -> User A"))
    
    # Memory recall check for User B
    console.print("\n[bold magenta]>>> Memory Recall Check: User B (Somying) <<<[/bold magenta]")
    msg_b2 = "ช่วยสรุปข้อมูลของฉันที่แจ้งไปให้หน่อยค่ะ"
    console.print(f"[bold magenta]User B:[/bold magenta] {msg_b2}")
    res_b2 = agent.invoke({"messages": [HumanMessage(content=msg_b2)], "session_id": session_b}, config={"configurable": {"thread_id": session_b}})
    reply_b2 = safe_extract_text(res_b2["messages"][-1].content)
    console.print(Panel(reply_b2, title="Agent Memory Verification -> User B"))
    
    # Validation assertion
    has_somchai_in_a = "สมชาย" in reply_a2
    no_somying_in_a = "สมหญิง" not in reply_a2
    has_somying_in_b = "สมหญิง" in reply_b2
    no_somchai_in_b = "สมชาย" not in reply_b2
    
    console.print("\n[bold yellow]Session Isolation Assertion Results:[/bold yellow]")
    console.print(f" • User A remembers Somchai: [bold green]{has_somchai_in_a}[/bold green]")
    console.print(f" • User A context has NO leak of Somying: [bold green]{no_somying_in_a}[/bold green]")
    console.print(f" • User B remembers Somying: [bold green]{has_somying_in_b}[/bold green]")
    console.print(f" • User B context has NO leak of Somchai: [bold green]{no_somchai_in_b}[/bold green]")
    
    if has_somchai_in_a and no_somying_in_a and has_somying_in_b and no_somchai_in_b:
        console.print("[bold green]SUCCESS: Session Separation & Memory Isolation Verified 100%![/bold green]")
    else:
        console.print("[bold red]FAILED: Context leaked between sessions![/bold red]")


if __name__ == "__main__":
    console.print("[bold green]Initializing InsureX AI Sales Agent Evaluation Suite...[/bold green]")
    agent = get_sales_agent()
    
    run_test_case_1_rag_precision(agent)
    run_test_case_2_error_handling(agent)
    run_test_case_3_lead_collection(agent)
    run_test_case_4_session_separation(agent)
    
    print_separator("ALL EVALUATION TEST CASES COMPLETED SUCCESSFULLY")
