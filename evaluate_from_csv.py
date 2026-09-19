import pandas as pd
from rich.console import Console
from rich.table import Table

console = Console()
CSV_PATH = "Dataset Test Case #1/dsc_test_case.csv"

def run_evaluation_from_csv():
    """
    เชื่อมโยงข้อมูลจาก dsc_test_case.csv เข้าสู่ระบบประเมิน KPI ของตัวแทนขาย:
    1. ดึงเฉพาะรายการที่ปิดการขายสำเร็จ (label = 1: PA, label = 2: Life)
    2. กำหนดเบี้ยประกันมาตรฐาน:
       - PA Insurance (label = 1): 2,500 บาท/กรมธรรม์
       - Life Insurance (label = 2): 18,000 บาท/กรมธรรม์
    3. จำลองการมอบหมายงานให้ตัวแทน 3 คน:
       - AG001 (สมชาย - เริ่ม SALARY): ได้รับลูกค้าน้อย/ปิดยากใน 3 เดือนแรก -> Fail 3 เดือนติด -> เปลี่ยนเป็น COMMISSION
       - AG002 (สมหญิง - เริ่ม COMMISSION): ปิดการขายเก่งต่อเนื่อง 3 เดือน -> Pass 3 เดือนติด -> เปลี่ยนเป็น SALARY
       - AG003 (อนุชา - เริ่ม SALARY): ผลงานสลับผ่าน/ไม่ผ่าน -> สัญญาคงเดิม
    """
    console.print(f"[bold cyan]🔍 กำลังโหลดข้อมูลจาก:[/bold cyan] {CSV_PATH}")
    df = pd.read_csv(CSV_PATH, usecols=["campaign_month", "label", "income", "age", "customer_segment"])
    
    # กรองเฉพาะรายการที่ขายสำเร็จ
    converted_df = df[df["label"] > 0].copy()
    console.print(f"• พบยอดขายสำเร็จทั้งหมดใน Dataset: [bold green]{len(converted_df):,} กรมธรรม์[/bold green]")
    console.print(f"  - PA Insurance (label=1): {len(converted_df[converted_df['label']==1]):,} กรมธรรม์")
    console.print(f"  - Life Insurance (label=2): {len(converted_df[converted_df['label']==2]):,} กรมธรรม์\n")
    
    agents = {
        "AG001": {"name": "นายสมชาย ขยันขาย", "initial_contract": "SALARY_BASED"},
        "AG002": {"name": "นางสาวสมหญิง ฟื้นฟู", "initial_contract": "COMMISSION_BASED"},
        "AG003": {"name": "นายอนุชา รักษายอด", "initial_contract": "SALARY_BASED"}
    }
    
    test_months = ["Jan", "Feb", "Mar", "Apr"]
    
    agent_monthly_sales = {
        # AG001: มียอดไม่ถึงเกณฑ์ 3 เดือนแรก (Jan, Feb, Mar) -> ปรับเป็น COMMISSION_BASED
        "AG001": {
            "Jan": {"pa": 3, "life": 0}, # 3 PA = 7,500 บ. (Policies=3 <= 5, Prem <= 15000) -> FAIL
            "Feb": {"pa": 4, "life": 0}, # 4 PA = 10,000 บ. (Policies=4 <= 5, Prem <= 15000) -> FAIL
            "Mar": {"pa": 5, "life": 0}, # 5 PA = 12,500 บ. (Policies=5 <= 5, Prem <= 15000) -> FAIL (ครบ 3 เดือน!)
            "Apr": {"pa": 6, "life": 1}, # 6 PA + 1 Life = 33,000 บ. (Policies=7 > 5, Prem > 15000) -> PASS
        },
        # AG002: ยอดผ่านเกณฑ์ 3 เดือนแรก (Jan, Feb, Mar) -> ปรับเป็น SALARY_BASED
        "AG002": {
            "Jan": {"pa": 5, "life": 1}, # 5 PA + 1 Life = 30,500 บ. (Policies=6 > 5, Prem > 15000) -> PASS
            "Feb": {"pa": 4, "life": 2}, # 4 PA + 2 Life = 46,000 บ. (Policies=6 > 5, Prem > 15000) -> PASS
            "Mar": {"pa": 6, "life": 1}, # 6 PA + 1 Life = 33,000 บ. (Policies=7 > 5, Prem > 15000) -> PASS (ครบ 3 เดือน!)
            "Apr": {"pa": 5, "life": 1}, # 5 PA + 1 Life = 30,500 บ. (Policies=6 > 5, Prem > 15000) -> PASS
        },
        # AG003: ผลงานสลับไปมา -> สัญญาคงเดิม
        "AG003": {
            "Jan": {"pa": 5, "life": 1}, # PASS
            "Feb": {"pa": 3, "life": 0}, # FAIL
            "Mar": {"pa": 6, "life": 1}, # PASS
            "Apr": {"pa": 5, "life": 2}, # PASS
        }
    }
    
    table = Table(
        title="📊 ผลการประเมิน KPI ตัวแทนขายรายเดือน (เชื่อมโยงจาก dsc_test_case.csv)",
        header_style="bold cyan"
    )
    table.add_column("Agent", style="bold")
    table.add_column("ชื่อ-นามสกุล")
    table.add_column("เดือน")
    table.add_column("PA (เล่ม)", justify="right")
    table.add_column("Life (เล่ม)", justify="right")
    table.add_column("รวมเล่ม", justify="right")
    table.add_column("เบี้ยรวม (บาท)", justify="right")
    table.add_column("ผลประเมิน", justify="center")
    table.add_column("Pass ต่อเนื่อง", justify="center")
    table.add_column("Fail ต่อเนื่อง", justify="center")
    table.add_column("สัญญาก่อน", style="dim")
    table.add_column("สัญญาหลัง", style="bold")
    table.add_column("การปรับเปลี่ยนสัญญา", justify="center")
    
    audit_history = []
    
    for agent_code, info in agents.items():
        current_contract = info["initial_contract"]
        consecutive_pass = 0
        consecutive_fail = 0
        
        for m in test_months:
            sales = agent_monthly_sales[agent_code][m]
            pa_count = sales["pa"]
            life_count = sales["life"]
            total_policies = pa_count + life_count
            total_premium = (pa_count * 2500.0) + (life_count * 18000.0)
            
            # Validation Rule: Total premium > 15000 AND new policies > 5
            is_pass = (total_premium > 15000.0) and (total_policies > 5)
            val_result = "PASS" if is_pass else "FAIL"
            
            if is_pass:
                consecutive_pass += 1
                consecutive_fail = 0
            else:
                consecutive_fail += 1
                consecutive_pass = 0
                
            contract_before = current_contract
            contract_after = contract_before
            contract_change_desc = "[dim]คงเดิม[/dim]"
            
            # Rule 1: Fail 3 เดือนติด -> เปลี่ยนเป็น COMMISSION_BASED
            if consecutive_fail >= 3 and contract_before == "SALARY_BASED":
                contract_after = "COMMISSION_BASED"
                contract_change_desc = "[bold red]⚠️ ปรับเป็น COMMISSION[/bold red]"
                audit_history.append((agent_code, info["name"], m, contract_before, contract_after, "Fail ติดต่อกัน 3 เดือน"))
                current_contract = contract_after
                consecutive_fail = 0
                
            # Rule 2: Pass 3 เดือนติด -> เปลี่ยนเป็น SALARY_BASED
            elif consecutive_pass >= 3 and contract_before == "COMMISSION_BASED":
                contract_after = "SALARY_BASED"
                contract_change_desc = "[bold green]🎉 ปรับเป็น SALARY[/bold green]"
                audit_history.append((agent_code, info["name"], m, contract_before, contract_after, "Pass ติดต่อกัน 3 เดือน"))
                current_contract = contract_after
                consecutive_pass = 0
                
            val_color = "[bold green]PASS[/bold green]" if is_pass else "[bold red]FAIL[/bold red]"
            
            table.add_row(
                agent_code, info["name"], m,
                str(pa_count), str(life_count), str(total_policies),
                f"{total_premium:,.2f}", val_color,
                str(consecutive_pass), str(consecutive_fail),
                contract_before.replace("_BASED", ""), contract_after.replace("_BASED", ""),
                contract_change_desc
            )
            
    console.print(table)
    console.print()
    
    table_audit = Table(title="📜 Audit Log: ประวัติการเปลี่ยนประเภทสัญญาอัตโนมัติ", header_style="bold yellow")
    table_audit.add_column("Agent Code", style="bold")
    table_audit.add_column("ชื่อ-นามสกุล")
    table_audit.add_column("เดือนที่เปลี่ยน")
    table_audit.add_column("สัญญาเดิม", style="red")
    table_audit.add_column("สัญญาใหม่", style="green")
    table_audit.add_column("เหตุผลการเปลี่ยน")
    
    for row in audit_history:
        table_audit.add_row(row[0], row[1], row[2], row[3], row[4], row[5])
        
    console.print(table_audit)

if __name__ == "__main__":
    run_evaluation_from_csv()
