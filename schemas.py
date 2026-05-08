from pydantic import BaseModel, EmailStr

class RegisterModel(BaseModel):
    email: EmailStr
    password: str
    role: str

class LoginModel(BaseModel):
    email: EmailStr
    password: str

class ChildModel(BaseModel):
    name: str
    age: int

class AssignDoctorModel(BaseModel):
    child_id: int
    doctor_id: int

class ResultModel(BaseModel):
    child_id: int
    word_id: int
    is_pass: bool
    fluency_score: float