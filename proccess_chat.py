import os

import time
import requests
import openai
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse, RedirectResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

jeno = FastAPI()

client = openai.OpenAI(api_key=os.getenv('API_KEY'))

bot_id = None
user2thread = {}

try:
    my_assistants = client.beta.assistants.list()
    assert os.getenv('CALLBOT_NAME') in map(lambda x: x.name, my_assistants)
    for _asst in my_assistants:
        if _asst.name == os.getenv('CALLBOT_NAME'):
            bot_id = _asst.id
            print(bot_id)
            break
except Exception as e:
    print(e)


def get_bot():
    global bot_id

    if bot_id is not None:
        return bot_id
    
    try:
        my_assistants = client.beta.assistants.list()
        print(list(map(lambda x: x.name, my_assistants)))
        assert os.getenv('CALLBOT_NAME') in map(lambda x: x.name, my_assistants)
        for _asst in my_assistants:
            if _asst.name == os.getenv('CALLBOT_NAME'):
                bot_id = _asst.id
    
    except Exception as e:
        print(e)


def get_thread_id(user_id):
    if user_id not in user2thread:
        thread = client.beta.threads.create()
        user2thread[user_id] = thread.id

    return user2thread[user_id]


def send_message(answer, thread_id):
    bot_id = get_bot()
    if bot_id is None:
        raise HTTPException(status_code=500, detail="Bot is not found.")

    run = client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=bot_id,
        instructions=answer.text
    )
    return run


class UserAnswer(BaseModel):
    text: str


@jeno.post("/call/")
async def audio_answer(answer: UserAnswer, request: Request):
    global bot_id

    auth_header = request.headers.get("Authorization")
    if auth_header:
        auth_token = auth_header
    else:
        raise HTTPException(status_code=400, detail="Please provide auth token.")
    try:
        thread_id = get_thread_id(auth_token)
        if not answer.text:
            answer = UserAnswer(text=os.getenv('START_PIPELINE'))
        run = send_message(answer, thread_id)
        while run.status in ['queued', 'in_progress']:
            run = client.beta.threads.runs.retrieve(
                thread_id=thread_id, run_id=run.id,
                )

        if run.status != 'completed':
            raise HTTPException(status_code=500,
                                detail='Message is not proccessed. Please try again.'
                            )
        try:
            messages = client.beta.threads.messages.list(
                        thread_id=thread_id, limit=1
                        )
            text_response = messages.data[0].content[0].dict()['text']['value']
    
            tts_response = client.audio.speech.create(model="tts-1",
                                                  input=text_response, voice='',
                                                  speed=1.4,
                                                  )
        except Exception as err:    
            raise HTTPException(status_code=500,
                                detail=f'Audio_data error {err}',
                            )


        ts = int(time.time())
        tts_response.stream_to_file(f'./{auth_token}_{ts}.mp3')

        return FileResponse(f'./{auth_token}_{ts}.mp3')

    except Exception as er:
        raise HTTPException(status_code=500, detail=str(er))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(jeno, host="0.0.0.0", port=8000)

