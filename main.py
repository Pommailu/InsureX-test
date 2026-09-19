import sys
import os
from langchain_core.messages import HumanMessage
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from rich.prompt import Prompt

import config
from agent_workflow import get_sales_agent, safe_extract_text
from lead_db import get_lead_db

console = Console()

BANNER = """
[bold cyan]╔════════════════════════════════════════════════════════════════════════════╗[/bold cyan]
[bold cyan]║[/bold cyan]       [bold yellow]InsureX AI Sales Agent — ระบบผู้ช่วยฝ่ายขายและให้คำปรึกษาประกันภัย[/bold yellow]       [bold cyan]║[/bold cyan]
[bold cyan]║[/bold cyan]     [dim]Powered by LangChain, LangGraph, ChromaDB, MCP Tooling & SQLite[/dim]      [bold cyan]║[/bold cyan]
[bold cyan]╚════════════════════════════════════════════════════════════════════════════╝[/bold cyan]
"""

HELP_TEXT = """
[bold yellow]คำสั่งพิเศษที่สามารถใช้งานได้:[/bold yellow]
  [bold green]/session <id>[/bold green]  : สลับ Session ID / ผู้ใช้งาน (ทดสอบ Session Separation)
  [bold green]/leads[/bold green]         : แสดงรายการข้อมูลลูกค้า (Lead) ทั้งหมดที่บันทึกใน SQLite
  [bold green]/info[/bold green]          : ดูสถานะของ Session และ Configuration ปัจจุบัน
  [bold green]/test[/bold green]          : รันชุดทดสอบความถูกต้องอัตโนมัติ (Evaluation Test Suite)
  [bold green]/help[/bold green]          : แสดงคำแนะนำการใช้งาน
  [bold green]/exit[/bold green]          : ออกจากโปรแกรม
"""

def show_all_leads():
    db = get_lead_db()
    leads = db.get_all_leads()
    if not leads:
        console.print("[yellow]ยังไม่มีข้อมูลลูกค้าบันทึกในฐานข้อมูล SQLite[/yellow]")
        return
    
    table = Table(title="[bold green]ฐานข้อมูลลูกค้าผู้มุ่งหวัง (Customer Leads Database)[/bold green]")
    table.add_column("ID", style="cyan", justify="center")
    table.add_column("Session", style="dim")
    table.add_column("ชื่อ-นามสกุล", style="bold white")
    table.add_column("อาชีพ", style="magenta")
    table.add_column("รายได้/เดือน", style="green")
    table.add_column("เบอร์ติดต่อ", style="yellow")
    table.add_column("สินค้าที่สนใจ", style="blue")
    table.add_column("บันทึกเมื่อ", style="dim")
    
    for row in leads:
        table.add_row(
            str(row.get("id")),
            str(row.get("session_id")),
            str(row.get("name")),
            str(row.get("occupation")),
            str(row.get("income")),
            str(row.get("phone_number")),
            str(row.get("product_interest") or "-"),
            str(row.get("created_at"))[:19]
        )
    console.print(table)

def main():
    console.clear()
    console.print(BANNER)
    console.print(HELP_TEXT)
    
    agent = get_sales_agent()
    current_session = "customer_session_001"
    
    console.print(f"[bold blue]Active Session:[/bold blue] [bold green]{current_session}[/bold green]\n")
    console.print("[dim]พิมพ์ข้อความเพื่อเริ่มสนทนากับน้องอินชัวร์ (หรือพิมพ์ /help เพื่อดูคำสั่ง)[/dim]\n")
    
    while True:
        try:
            user_input = Prompt.ask(f"[bold cyan]คุณ ({current_session})[/bold cyan]").strip()
            if not user_input:
                continue
                
            # Command Handling
            if user_input.lower() in ["/exit", "exit", "quit", ":q"]:
                console.print("\n[bold green]ขอบคุณที่ใช้บริการ InsureX AI Sales Agent ครับ สวัสดีครับ![/bold green]")
                break
            elif user_input.lower() == "/help":
                console.print(HELP_TEXT)
                continue
            elif user_input.lower() == "/leads":
                show_all_leads()
                continue
            elif user_input.lower().startswith("/session"):
                parts = user_input.split(maxsplit=1)
                if len(parts) > 1 and parts[1].strip():
                    current_session = parts[1].strip()
                    console.print(f"[bold green]สลับไปที่ Session ID:[/bold green] [bold yellow]{current_session}[/bold yellow]")
                else:
                    console.print(f"[bold blue]Current Session ID:[/bold blue] {current_session}")
                continue
            elif user_input.lower() == "/info":
                console.print(Panel(
                    f"[bold]Model:[/bold] {config.GOOGLE_MODEL}\n"
                    f"[bold]Embedding Model:[/bold] {config.GOOGLE_EMBEDDING_MODEL}\n"
                    f"[bold]Vector DB:[/bold] ChromaDB ({config.CHROMA_PERSIST_DIR})\n"
                    f"[bold]Lead DB:[/bold] SQLite ({config.SQLITE_DB_PATH})\n"
                    f"[bold]Active Session:[/bold] {current_session}",
                    title="System Configuration"
                ))
                continue
            elif user_input.lower() == "/test":
                import demo_test
                demo_test.run_test_case_1_rag_precision(agent)
                demo_test.run_test_case_2_error_handling(agent)
                demo_test.run_test_case_3_lead_collection(agent)
                demo_test.run_test_case_4_session_separation(agent)
                continue

            # Run Agent turn
            thread_cfg = {"configurable": {"thread_id": current_session}}
            state_input = {
                "messages": [HumanMessage(content=user_input)],
                "session_id": current_session
            }
            
            with console.status("[bold green]น้องอินชัวร์กำลังคิด...[/bold green]", spinner="dots"):
                res = agent.invoke(state_input, config=thread_cfg)
                
            reply = safe_extract_text(res["messages"][-1].content)
            intent = res.get("customer_intent", "")
            lead_saved = res.get("lead_saved", False)
            
            status_tag = f"[dim]Intent: {intent}[/dim]"
            if lead_saved:
                status_tag += " | [bold green]✓ Lead Saved to DB[/bold green]"
                
            console.print(Panel(
                Markdown(reply),
                title="[bold magenta]น้องอินชัวร์ (InsureX Sales Assistant)[/bold magenta]",
                subtitle=status_tag,
                border_style="cyan"
            ))
            console.print()

        except (KeyboardInterrupt, EOFError):
            console.print("\n[bold green]ขอบคุณที่ใช้บริการ InsureX AI Sales Agent ครับ สวัสดีครับ![/bold green]")
            break
        except Exception as e:
            console.print(f"[bold red]เกิดข้อผิดพลาด: {e}[/bold red]")

if __name__ == "__main__":
    main()
