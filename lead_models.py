import re
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator

class CustomerLead(BaseModel):
    """
    Structured customer lead model for InsureX sales agent.
    Captures the 4 core requirements: Name, Occupation, Income, and Phone Number.
    """
    name: Optional[str] = Field(
        default=None,
        description="ชื่อและนามสกุลของลูกค้า (Full Name)"
    )
    occupation: Optional[str] = Field(
        default=None,
        description="อาชีพหรือลักษณะการทำงานของลูกค้า เช่น พนักงานบริษัท, ธุรกิจส่วนตัว, ฟรีแลนซ์, ข้าราชการ"
    )
    income: Optional[str] = Field(
        default=None,
        description="รายได้ต่อเดือน หรือฐานเงินเดือนของลูกค้า เช่น 35,000 บาท, 50,000 - 70,000 บาท/เดือน"
    )
    phone_number: Optional[str] = Field(
        default=None,
        description="เบอร์โทรศัพท์ติดต่อของลูกค้า (10 หลักขึ้นต้นด้วย 0 เช่น 0812345678, 089-999-8888)"
    )
    product_interest: Optional[str] = Field(
        default="ประกันภัยทั่วไป",
        description="ชื่อผลิตภัณฑ์ประกันที่ลูกค้าให้ความสนใจ เช่น ประกันชีวิต FWD, ประกันสุขภาพ, ประกันอุบัติเหตุ"
    )
    notes: Optional[str] = Field(
        default=None,
        description="บันทึกเพิ่มเติม เช่น ช่วงเวลาที่สะดวกให้ติดต่อกลับ"
    )

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        # Remove common separators: spaces, dashes, parentheses
        cleaned = re.sub(r"[\s\-\(\)]", "", v)
        # Check standard Thai phone format
        if re.match(r"^0\d{8,9}$", cleaned):
            return cleaned
        return v.strip()

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        cleaned = v.strip()
        return cleaned if len(cleaned) > 1 else None

    @property
    def is_complete(self) -> bool:
        """Checks if all 4 required fields are filled and valid."""
        return bool(
            self.name and self.name.strip() and
            self.occupation and self.occupation.strip() and
            self.income and self.income.strip() and
            self.phone_number and self.phone_number.strip()
        )

    def get_missing_fields_th(self) -> List[str]:
        """Returns list of missing required fields in Thai for agent clarification."""
        missing = []
        if not self.name or not self.name.strip():
            missing.append("ชื่อ-นามสกุล")
        if not self.occupation or not self.occupation.strip():
            missing.append("อาชีพ")
        if not self.income or not self.income.strip():
            missing.append("รายได้ต่อเดือน")
        if not self.phone_number or not self.phone_number.strip():
            missing.append("เบอร์โทรศัพท์ติดต่อ")
        return missing

    def merge_with(self, new_lead: "CustomerLead") -> "CustomerLead":
        """Merges new extracted fields into existing partial lead data."""
        return CustomerLead(
            name=new_lead.name or self.name,
            occupation=new_lead.occupation or self.occupation,
            income=new_lead.income or self.income,
            phone_number=new_lead.phone_number or self.phone_number,
            product_interest=new_lead.product_interest or self.product_interest,
            notes=new_lead.notes or self.notes,
        )
