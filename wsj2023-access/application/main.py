from xmlrpc.client import Boolean
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware  # NEW
from pydantic import BaseSettings, BaseModel, EmailStr, constr
from typing import Optional, List, Tuple, Dict, Any, Union
from fastapi.staticfiles import StaticFiles
from enum import Enum
from datetime import timedelta
import pydantic
from requests_cache import CachedSession
from fastapi_pagination import Page, add_pagination, paginate

import datetime
import json

session = CachedSession('access_cache', expire_after=timedelta(minutes=5), backend='memory')

class Settings(BaseSettings):
    app_name: str = "ScoutView"
    scoutnet_base: str = 'https://scoutnet.se/api'
    scoutnet_activity_id: int = 0
    scoutnet_participants_key: str = ''
    scoutnet_questions_key: str = ''
    scoutnet_checkin_key: str = ''

    class Config:
        env_file = ".env"

class View(str, Enum):
    pass

class Participant(BaseModel):
    member_no: int
    first_name: str
    last_name: str
    registration_date: datetime.datetime
    cancelled_date: Optional[datetime.datetime]
    sex: int
    date_of_birth: datetime.date
    primary_email: Union[EmailStr, constr(max_length=0)]
    questions: Any


class Question(BaseModel):
    id: int
    tab_id: int
    tab_title: Optional[str]
    tab_description: Optional[str]
    section_id: int
    section_title: Optional[str]
    filterable: Boolean
    status: Optional[Boolean]
    question: str
    description: str
    type: str
    default_value: Optional[str]
    choices: Optional[Any]


class ParticipantsOut(BaseModel):
    length: int
    participants: List[Participant]


def get_participants():
    url = f'{settings.scoutnet_base}/project/get/participants?id={settings.scoutnet_activity_id}&key={settings.scoutnet_participants_key}'
    print(f'Fetching: {url}')
    r = session.get(url)
    data = json.loads(r.text)
    return list(data['participants'].values())

def clean_participants_cache():
    session.remove_expired_responses(expire_after=0)


settings = Settings()
app = FastAPI(reload=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/info")
async def info(request: Request):
    headers = request.headers
    return {
        "app_name": settings.app_name,
        "activity": settings.scoutnet_activity_id,
        "headers": headers,
    }

@app.get("/participants", response_model=Page[Participant])
def participants(form: Optional[int] = None, q: Optional[int] = None, q_val: Optional[int] = None):
    qualifier = None
    if form == 5085: # deltagare
        qualifier = "24549"
    elif form == 5734: # ist
        qualifier = "25654"
    else: # unknown form (yet)
        return paginate([])

    p = get_participants()
    p = list(filter(lambda x: qualifier in x['questions'], p))
    if (q != 0):
        p = list(filter(lambda x: str(q) in x['questions'] and x['questions'][str(q)] == str(q_val), p))
    p = sorted(p, key=lambda x : f"{x['registration_date']} {x['member_no']}")
    return paginate(p)

@app.get("/questions", response_model=List[Question])
def questions(form_id: int) -> Dict[int, Question]:
    url = f'{settings.scoutnet_base}/project/get/questions?id={settings.scoutnet_activity_id}&key={settings.scoutnet_questions_key}&form_id={form_id}'
    print(f'Fetching: {url}')
    r = session.get(url)
    data = json.loads(r.text)['questions']
    tabs = data['tabs']
    sections = data['sections']
    status_tabs = [v['id'] for (_,v) in data['tabs'].items() if v['title'] == 'Status']
    del data['tabs']
    del data['sections']
    questions = []
    for id, v in data.items():
        questions.append(dict({
            'id': id,
            'status': True if (v['tab_id'] in status_tabs) else False,
            'filterable': v['type'] == 'choice',
            'tab_title': tabs[str(v['tab_id'])]['title'] if str(v['tab_id']) in tabs else '',
            'tab_description': tabs[str(v['tab_id'])]['description'] if str(v['tab_id']) in tabs else '',
            'section_title': sections[str(v['section_id'])]['title'] if str(v['section_id']) in sections else '',
            }, **v))
    questions = sorted(questions, key=lambda x : f"{x['tab_id']} {x['section_id']}")
    return questions

@app.get("/forms", response_model=Dict[int, str])
def forms() -> Dict[int, str]:
    url = f'{settings.scoutnet_base}/project/get/questions?id={settings.scoutnet_activity_id}&key={settings.scoutnet_questions_key}'
    print(f'Fetching: {url}')
    r = session.get(url)
    data = json.loads(r.text)['forms']
    print(data)
    res = {key: value['title'] for (key, value) in data.items()}
    # print(res)
    return res

@app.post("/update_status", response_model=Boolean)
def update_status(member_no: int, answers: Dict[int, str]) -> Boolean:
    url = f'{settings.scoutnet_base}/project/checkin?id={settings.scoutnet_activity_id}&key={settings.scoutnet_checkin_key}'
    ans = {k:{'value': v} for (k,v) in answers.items()}
    body = {str(member_no): {'questions': ans}}
    print(f'Posting {body} to {url}')
    r = session.post(url, json.dumps(body), headers={'Content-Type': 'application/json'})
    data = json.loads(r.text)
    clean_participants_cache()
    print(data)
    return r.ok


add_pagination(app)
# Place After All Other Routes
app.mount('', StaticFiles(directory="../client/public/", html=True), name="static")