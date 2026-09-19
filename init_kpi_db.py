import sqlite3
import os
from rich.console import Console
from rich.table import Table

DB_PATH = "sales_performance.db"
SQL_SCHEMA_FILE = "schema_kpi_contract.sql"

console = Console()

def init_database():
    """สร้างตารางในฐานข้อมูลจากไฟล์ schema_kpi_contract.sql"""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    with open(SQL_SCHEMA_FILE, "r", encoding="utf-8") as f:
        schema_sql = f.read()
        
    cursor.executescript(schema_sql)
    conn.commit()
    conn.close()
    console.print(f"[bold green]✓ สร้างฐานข้อมูลสำเร็จ:[/bold green] {DB_PATH}")

def seed_agents_and_sales():
    """เพิ่มข้อมูลตัวอย่าง Agent และรายการขายในแต่ละเดือน"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. เพิ่มตัวแทนขาย 3 คน
    agents_data = [
        ("agt_001", "AG001", "นายสมชาย ขยันขาย", "SALARY_BASED", "2026-01-01"),
        ("agt_002", "AG002", "นางสาวสมหญิง ฟื้นฟู", "COMMISSION_BASED", "2026-01-01"),
        ("agt_003", "AG003", "นายอนุชา รักษายอด", "SALARY_BASED", "2026-01-01"),
    ]
    cursor.executemany("""
        INSERT INTO agents (agent_id, agent_code, full_name, current_contract_type, contract_effective_date)
        VALUES (?, ?, ?, ?, ?)
    """, agents_data)
    
    # 2. จำลองข้อมูลยอดขายรายเดือน (Year-Month, Total Premium, Policy Count)
    monthly_sales_mock = {
        "agt_001": [
            ("2026-06", 12000.00, 4),  # FAIL (Streak: 1)
            ("2026-07", 14500.00, 5),  # FAIL (Streak: 2)
            ("2026-08", 10000.00, 3),  # FAIL (Streak: 3 -> ปรับเป็น COMMISSION_BASED)
            ("2026-09", 11000.00, 4),  # ต่อเนื่องในสัญญาใหม่
        ],
        "agt_002": [
            ("2026-06", 28000.00, 7),  # PASS (Streak: 1)
            ("2026-07", 32000.00, 8),  # PASS (Streak: 2)
            ("2026-08", 24000.00, 6),  # PASS (Streak: 3 -> ปรับเป็น SALARY_BASED)
            ("2026-09", 26000.00, 7),  # ต่อเนื่องในสัญญาใหม่
        ],
        "agt_003": [
            ("2026-06", 18000.00, 6),  # PASS
            ("2026-07", 13000.00, 4),  # FAIL (รีเซ็ต Pass=0, Fail=1)
            ("2026-08", 22000.00, 7),  # PASS (รีเซ็ต Fail=0, Pass=1)
            ("2026-09", 19500.00, 6),  # PASS
        ]
    }
    
    # 3. รันประเมิน KPI รายเดือน
    for agent_id, months in monthly_sales_mock.items():
        cursor.execute("SELECT current_contract_type FROM agents WHERE agent_id = ?", (agent_id,))
        current_contract = cursor.fetchone()[0]
        
        consecutive_pass = 0
        consecutive_fail = 0
        
        for ym, total_prem, pol_count in months:
            is_prem_pass = total_prem > 15000.00
            is_pol_pass = pol_count > 5
            is_pass = is_prem_pass and is_pol_pass
            val_result = "PASS" if is_pass else "FAIL"
            
            if is_pass:
                consecutive_pass += 1
                consecutive_fail = 0
            else:
                consecutive_fail += 1
                consecutive_pass = 0
                
            contract_before = current_contract
            contract_after = contract_before
            contract_changed = False
            change_reason = None
            
            # กฎข้อ 1: Fail ติดต่อกัน 3 เดือน -> ปรับเป็น COMMISSION_BASED
            if consecutive_fail >= 3 and contract_before == "SALARY_BASED":
                contract_after = "COMMISSION_BASED"
                contract_changed = True
                change_reason = "FAILED_3_CONSECUTIVE_MONTHS"
                
            # กฎข้อ 2: Pass ติดต่อกัน 3 เดือน -> ปรับเป็น SALARY_BASED
            elif consecutive_pass >= 3 and contract_before == "COMMISSION_BASED":
                contract_after = "SALARY_BASED"
                contract_changed = True
                change_reason = "PASSED_3_CONSECUTIVE_MONTHS"
                
            cursor.execute("""
                INSERT INTO agent_monthly_performance (
                    agent_id, campaign_month, total_premium, new_policy_count,
                    is_premium_passed, is_policy_passed, validation_result,
                    consecutive_pass_months, consecutive_fail_months,
                    contract_type_before, contract_type_after, contract_changed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                agent_id, ym, total_prem, pol_count,
                is_prem_pass, is_pol_pass, val_result,
                consecutive_pass, consecutive_fail,
                contract_before, contract_after, contract_changed
            ))
            perf_id = cursor.lastrowid
            
            if contract_changed:
                cursor.execute("""
                    INSERT INTO agent_contract_history (
                        agent_id, triggered_by_performance_id, previous_contract_type,
                        new_contract_type, effective_month, change_reason
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (agent_id, perf_id, contract_before, contract_after, ym, change_reason))
                
                cursor.execute("""
                    UPDATE agents 
                    SET current_contract_type = ?, contract_effective_date = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE agent_id = ?
                """, (contract_after, f"{ym}-01", agent_id))
                
                current_contract = contract_after
                if change_reason == "FAILED_3_CONSECUTIVE_MONTHS":
                    consecutive_fail = 0
                else:
                    consecutive_pass = 0

    conn.commit()
    conn.close()
    console.print("[bold green]✓ ประมวลผลและจำลองข้อมูลยอดขายรายเดือนสำเร็จ[/bold green]\n")

def display_report():
    """แสดงรายงานผลการประเมินรายเดือนและประวัติการเปลี่ยนสัญญา"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    table_agents = Table(title="1. ข้อมูลตัวแทนขายและสัญญาปัจจุบัน (Current Agent Contracts)", header_style="bold cyan")
    table_agents.add_column("Agent Code", style="bold")
    table_agents.add_column("ชื่อ-นามสกุล")
    table_agents.add_column("ประเภทสัญญาปัจจุบัน", style="bold yellow")
    table_agents.add_column("วันที่มีผล")
    table_agents.add_column("สถานะ", style="green")
    
    for row in cursor.execute("SELECT agent_code, full_name, current_contract_type, contract_effective_date, status FROM agents"):
        table_agents.add_row(row[0], row[1], row[2], str(row[3]), row[4])
    console.print(table_agents)
    console.print()

    table_perf = Table(title="2. ตารางสรุปผลงานและการประเมิน KPI รายเดือน (Monthly Validation Tracking)", header_style="bold magenta")
    table_perf.add_column("Agent", style="bold")
    table_perf.add_column("เดือน")
    table_perf.add_column("เบี้ยรวม (บาท)", justify="right")
    table_perf.add_column("กรมธรรม์", justify="right")
    table_perf.add_column("ผลประเมิน", justify="center")
    table_perf.add_column("Pass สะสม", justify="center")
    table_perf.add_column("Fail สะสม", justify="center")
    table_perf.add_column("สัญญาก่อน", style="dim")
    table_perf.add_column("สัญญาหลัง", style="bold")
    table_perf.add_column("ปรับสัญญา?", justify="center")
    
    query_perf = """
        SELECT a.agent_code, p.campaign_month, p.total_premium, p.new_policy_count,
               p.validation_result, p.consecutive_pass_months, p.consecutive_fail_months,
               p.contract_type_before, p.contract_type_after, p.contract_changed
        FROM agent_monthly_performance p
        JOIN agents a ON p.agent_id = a.agent_id
        ORDER BY a.agent_code, p.campaign_month
    """
    for row in cursor.execute(query_perf):
        val_color = "[bold green]PASS[/bold green]" if row[4] == "PASS" else "[bold red]FAIL[/bold red]"
        changed_mark = "[bold red]⚠️ เปลี่ยนสัญญา[/bold red]" if row[9] else "[dim]คงเดิม[/dim]"
        table_perf.add_row(
            row[0], row[1], f"{row[2]:,.2f}", str(row[3]),
            val_color, str(row[5]), str(row[6]),
            row[7], row[8], changed_mark
        )
    console.print(table_perf)
    console.print()

    table_history = Table(title="3. ประวัติการปรับเปลี่ยนประเภทสัญญา (Contract Audit History)", header_style="bold yellow")
    table_history.add_column("Agent Code", style="bold")
    table_history.add_column("สัญญาเดิม", style="red")
    table_history.add_column("สัญญาใหม่", style="green")
    table_history.add_column("เดือนที่มีผล")
    table_history.add_column("สาเหตุการเปลี่ยนสัญญา (Reason)")
    
    query_history = """
        SELECT a.agent_code, h.previous_contract_type, h.new_contract_type,
               h.effective_month, h.change_reason
        FROM agent_contract_history h
        JOIN agents a ON h.agent_id = a.agent_id
        ORDER BY h.history_id
    """
    for row in cursor.execute(query_history):
        table_history.add_row(row[0], row[1], row[2], str(row[3]), row[4])
    console.print(table_history)
    
    conn.close()

if __name__ == "__main__":
    init_database()
    seed_agents_and_sales()
    display_report()
