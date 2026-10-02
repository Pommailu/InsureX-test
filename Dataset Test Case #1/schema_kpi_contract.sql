-- 1. ตารางข้อมูลตัวแทนขายและสัญญาปัจจุบัน (Agents)
CREATE TABLE IF NOT EXISTS agents (
    agent_id VARCHAR(36) PRIMARY KEY,
    agent_code VARCHAR(20) UNIQUE NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    current_contract_type VARCHAR(20) NOT NULL CHECK (current_contract_type IN ('SALARY_BASED', 'COMMISSION_BASED')),
    contract_effective_date DATE NOT NULL,
    status VARCHAR(20) DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'INACTIVE', 'TERMINATED')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. ตารางรายชื่อลูกค้าแคมเปญ (Campaign Leads - เชื่อมโยงโดยตรงกับ dsc_test_case.csv)
CREATE TABLE IF NOT EXISTS campaign_leads (
    lead_id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_month VARCHAR(10) NOT NULL,            -- เช่น 'Jan', 'Feb', 'Mar' (จาก dsc_test_case.csv)
    customer_segment VARCHAR(50),                   -- 'Lower Mass', 'Mass', 'Upper Mass'
    marital_sta VARCHAR(20),                        -- สถานะสมรส
    main_occupation VARCHAR(100),                   -- อาชีพ
    gender VARCHAR(10),                             -- เพศ
    age DOUBLE,                                     -- อายุ
    income DECIMAL(12, 2),                          -- รายได้
    savacc_bal DECIMAL(12, 2),                      -- เงินฝากออมทรัพย์
    net_flow_30d DECIMAL(13, 2),                    -- กระแสเงินสุทธิ 30 วัน
    
    -- ผลการติดต่อเสนอขายในแคมเปญ (Campaign Outcome)
    -- 0 = ปฏิเสธ (Reject), 1 = ตกลงทำประกันอุบัติเหตุ (PA), 2 = ตกลงทำประกันชีวิต (Life)
    label INTEGER NOT NULL CHECK (label IN (0, 1, 2)),
    
    -- ตัวแทนขายที่ได้รับมอบหมายรายชื่อนี้ให้โทรติดต่อ
    assigned_agent_id VARCHAR(36),
    contacted_date DATE,
    
    FOREIGN KEY (assigned_agent_id) REFERENCES agents(agent_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_campaign_leads_agent_month ON campaign_leads(assigned_agent_id, campaign_month);
CREATE INDEX IF NOT EXISTS idx_campaign_leads_label ON campaign_leads(label);

-- 3. ตารางบันทึกการขายกรมธรรม์ที่สำเร็จ (Policy Sales Transactions - สร้างเมื่อ label in (1, 2))
CREATE TABLE IF NOT EXISTS policy_sales (
    policy_id INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_number VARCHAR(50) UNIQUE NOT NULL,
    lead_id INTEGER,                                -- เชื่อมโยงกับ lead ใน campaign_leads (dsc_test_case.csv)
    agent_id VARCHAR(36) NOT NULL,                  -- ตัวแทนผู้ปิดการขาย
    campaign_month VARCHAR(10) NOT NULL,            -- เดือนของแคมเปญ เช่น 'Jan', 'Feb'
    issue_date DATE NOT NULL,
    product_type VARCHAR(50) NOT NULL CHECK (product_type IN ('PA Insurance', 'Life Insurance')),
    premium_amount DECIMAL(12, 2) NOT NULL,         -- เบี้ยประกันภัย (เช่น PA=2,500, Life=18,000)
    policy_status VARCHAR(20) DEFAULT 'ACTIVE' CHECK (policy_status IN ('ACTIVE', 'CANCELLED', 'LAPSED')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (lead_id) REFERENCES campaign_leads(lead_id) ON DELETE SET NULL,
    FOREIGN KEY (agent_id) REFERENCES agents(agent_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_policy_sales_agent_month ON policy_sales(agent_id, campaign_month);

-- 4. ตารางสรุปผลงานและการประเมินรายเดือน (Agent Monthly Performance)
CREATE TABLE IF NOT EXISTS agent_monthly_performance (
    performance_id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id VARCHAR(36) NOT NULL,
    campaign_month VARCHAR(10) NOT NULL,            -- รอบเดือนประเมิน เช่น 'Jan', 'Feb'
    
    -- ผลรวมยอดขายในเดือนนั้น
    total_premium DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    new_policy_count INT NOT NULL DEFAULT 0,
    
    -- กฎการประเมินผล KPI (Validation Rules)
    -- เงื่อนไข: total_premium > 15000.00 AND new_policy_count > 5
    is_premium_passed BOOLEAN NOT NULL DEFAULT FALSE,
    is_policy_passed BOOLEAN NOT NULL DEFAULT FALSE,
    validation_result VARCHAR(10) NOT NULL CHECK (validation_result IN ('PASS', 'FAIL')),
    
    -- ตัวนับจำนวนเดือนต่อเนื่อง (Consecutive Counters)
    consecutive_pass_months INT NOT NULL DEFAULT 0,
    consecutive_fail_months INT NOT NULL DEFAULT 0,
    
    -- สถานะสัญญาก่อนและหลังประเมินในเดือนนี้
    contract_type_before VARCHAR(20) NOT NULL CHECK (contract_type_before IN ('SALARY_BASED', 'COMMISSION_BASED')),
    contract_type_after VARCHAR(20) NOT NULL CHECK (contract_type_after IN ('SALARY_BASED', 'COMMISSION_BASED')),
    contract_changed BOOLEAN NOT NULL DEFAULT FALSE,
    
    evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE (agent_id, campaign_month),
    FOREIGN KEY (agent_id) REFERENCES agents(agent_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_monthly_perf_agent_month ON agent_monthly_performance(agent_id, campaign_month);

-- 5. ตารางประวัติการเปลี่ยนแปลงสัญญา (Agent Contract Audit History)
CREATE TABLE IF NOT EXISTS agent_contract_history (
    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id VARCHAR(36) NOT NULL,
    triggered_by_performance_id INTEGER,
    previous_contract_type VARCHAR(20) NOT NULL,
    new_contract_type VARCHAR(20) NOT NULL,
    effective_month VARCHAR(10) NOT NULL,
    change_reason VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (agent_id) REFERENCES agents(agent_id) ON DELETE CASCADE,
    FOREIGN KEY (triggered_by_performance_id) REFERENCES agent_monthly_performance(performance_id)
);
