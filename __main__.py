from loguru import logger
from pydantic_settings import BaseSettings
from slack_bolt import App
from openai import OpenAI
import os
from dotenv import load_dotenv
import requests
import json
import re

from slack_bolt.adapter.socket_mode import SocketModeHandler

load_dotenv()


class MeddiccSettings(BaseSettings):
    """My skill is VASTED on zis team!"""
    SLACK_BOT_TOKEN: str
    SLACK_APP_TOKEN: str
    SIGNING_SECRET: str
    OPENAI_API_TOKEN: str
    GONG_SECRET: str
    GONG_ACCESS_KEY: str

SETTINGS = MeddiccSettings()

def clean_transcript(transcript):
    logger.info("Cleaning transcript")
    document = ""
    speakers = ""
    for i in transcript:
        subdocument = ""
        # subdocument += f"{i['speakerId']}:"
        for i in i['sentences']:
            subdocument += " " + i['text']

        document += subdocument
    logger.info("Cleaned transcript")
    return (document)


def pull_transcript(call_id="6559553088899773203") -> str:
    logger.info(f"Getting transcript for: {call_id}")
    assert SETTINGS.GONG_SECRET is not None, "GONG_SECRET is not set"
    assert SETTINGS.GONG_ACCESS_KEY is not None, "GONG_ACCESS_KEY is not set"

    url = "https://api.gong.io/v2/calls/transcript"

    payload = {
        "filter": {
            "callIds": [call_id]
        }
    }

    headers = {
        "Content-Type": "application/json"
    }
    response = requests.post(url, auth=(SETTINGS.GONG_ACCESS_KEY, SETTINGS.GONG_SECRET), headers=headers, data=json.dumps(payload))

    response.json()
    transcript = (response.json()['callTranscripts'][0]['transcript'])
    logger.info("Got transcript")
    return transcript


ai_client = OpenAI(api_key=SETTINGS.OPENAI_API_TOKEN)

def get_transcript_metadate(call_id) -> tuple[str, dict]:
    url = "https://api.gong.io/v2/calls/extensive"
    payload = {
        "contentSelector": {
        "context": "Extended",
        "contextTiming": ["Now"],
        "exposedFields": {
        "parties": True
        }
        },  
        "filter": {
        "callIds":[call_id]
        }
    }
    #    "fromDateTime": "2024-10-01T02:30:00-08:00",
    #   "toDateTime": "2024-10-02T23:59:00-08:00"
    headers = {
        "Content-Type": "application/json"
    }

    response = requests.post(url, auth=(SETTINGS.GONG_ACCESS_KEY, SETTINGS.GONG_SECRET), headers=headers, data = json.dumps(payload))
    
    #GET CALL ACCOUNT AND NAME
    account = ""
    opportunity = ""

    for i in response.json()['calls'][0]['context'][0]["objects"]:
        if i['objectType'] == 'Account':
            for j in i['fields']:
                if j['name'] == 'Name':
                    account = j['value']
                    break
        if i['objectType'] == 'Opportunity':
            for j in i['fields']:
                if j['name'] == 'Name':
                    opportunity = j['value']
                    break

    # GET PARTIES AND SPEAKER IDS

    speaker_id_dict = {}
    speakers = ""
    for i in response.json()['calls'][0]['parties']:
        speakers += (i['name'] if 'name' in i else 'Unknown') + ": " + (i['title'] if 'title' in i else 'None') + ", email: " + (i['emailAddress'] if 'emailAddress' in i else 'None') + ", affiliation: " + (i['affiliation'] if 'affiliation' in i else 'None') + " \n "
        if i['affiliation'] == 'External':
            speaker_id_dict[i['speakerId']] = (i['name'] if 'name' in i else 'Unknown') + ', ' + account
        elif i['affiliation'] == 'Internal':
            speaker_id_dict[i['speakerId']] = (i['name'] if 'name' in i else 'Unknown') + ', Vortexa'
        else:
            speaker_id_dict[i['speakerId']] = (i['name'] if 'name' in i else 'Unknown')
    speakers

    #TURN INTO A HEADER
    output_string = f"Call with Account: {account} \n Title: {opportunity} \n Speakers: \n {speakers}"
    return(output_string,speaker_id_dict)


        

def clean_transcript_updated(transcript,speaker_id_dict) -> str:
    document = ""
    speakers = ""
    for i in transcript:
        subdocument = ""
        subdocument += f" {speaker_id_dict[i['speakerId']]}:"
        for i in i['sentences']:
            subdocument += " " + i['text']

        document += subdocument + "\n"
    return(document)


def meddic_bot(input) -> str:
    logger.info("Calling openai api")
    sales_bot = ai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system",
             "content": """
            Brief
            Salesforce contains 7 large text fields for Sales execs to fill out after meetings where they are tasks to provide context and information to the deals they are working on which are: 

            M_Metrics - How will the prospect measure success? What quantifiable goals do they need to achieve? Set the stage by understanding how a prospect will measure the success of implementing your product and services. By understanding what they’re trying to achieve, teams can work backwards to offer tailored solution. These metrics enable you to describe the economic benefits of your solution. Once you know what metrics the customer cares about, you can prove how your solution provides a good return on investment (ROI). 
            M_EconomicBuyer - Who is the real decision-maker? Does the person I’m talking to have budget and authority to make the buy decision? Focus on the person who can “write the check” and create budget for innovative solutions. While teams need to respect everyone in the process, they should go above and beyond to please the economic buyer.
            M_IdentifyPain - What problem is the prospect trying to solve? What’s the risk in terms of lost revenue, opportunity cost, etc.? How soon before this problem becomes unbearable? Without a serious pain point that causes economic harm or risk to the business, prospects aren’t likely to purchase. Make sure you’ve clearly identified a prospect’s pain and how it impacts their business.
            M_DecisionCriteria - What’s driving their decision? Do we, the vendor, need to meet certain technical, budget, or ROI requirements? Companies must align economically, technically, and in values to seal the deal. Economically, the two organizations must align on price. Technically, the solution must solve their problem and finally, they must be aligned in values.
            M_DecisionProcess - Who is involved in the prospect’s buying process? What steps need to happen before a final decision? Does the process change based on the amount of money at stake? By understanding the decision process, sales teams can tailor their sales process to match the prospect’s buying process.
            M_Competition - Who else is the prospect considering, and how does our solution compare? Know your unique value proposition: your competitive advantages vis-a-vis the competition in solving the prospect’s pains and meeting their success metrics.
            M_Champion - Who is the lead contact or user who advocates for us and our products and drives engagement as well as usage 

            Goal
            To fill in MEDDICC using summarized Gong transcripts whether limited or to a full extent. This could be paired with an auto-opportunity creation tool if needed. With this goal, the aim is to:

            Save Sales Execs much time on admin
            Improve our deal understanding and data quality and 
            Standardize qualitative data input

            Example
            M_IdentifyPain - ‘ stakeholder X stated their organisation pain point is not enough clarity on clean products in the US market as well as dissatisfaction with a current provider: “Yeah, we just don’t have a good coverage upstream or downstream for cleans here in the US which is why we’re looking at Vortexa”’. 

            the output does not have to be an exact quote but a summary of the pain point and the quote that supports it. The more accurate the better.

            for every output please at the beginning include the quote
            "This information summerized by an AI and therefore may contains errors or inaccuracies"

            there is no need to include any other output exept the quote and the text fields
            """},
            {
                "role": "user",
                "content": input
            }
        ],
        response_format={"type": "text"}
    )
    logger.info("Got response from openai")
    return sales_bot.choices[0].message.content


def cowboy_bot(input):
    sales_bot = ai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system",
             "content": """
            You are a helpful assistant integrated with slack, who talks like a cowboy
            your name is meddic
            """},
            {
                "role": "user",
                "content": input
            }
        ],
        response_format={"type": "text"}
    )
    return sales_bot.choices[0].message.content


# Initializes your app with your bot token and signing secret
app = App(
    token=SETTINGS.SLACK_BOT_TOKEN,
    signing_secret=SETTINGS.SIGNING_SECRET
)


# Listens to incoming messages that contain "hello"
# To learn available listener arguments,
# visit https://tools.slack.dev/bolt-python/api-docs/slack_bolt/kwargs_injection/args.html


@app.event("app_mention")
def handle_app_mention(body, say, ack):
    ack()
    logger.info(f"Got request: {body}")

    text = str(body["event"]["text"]).split(">")[1]
    pattern = r'\d+$'
    match = re.search(pattern, text)
    if not match:
        say("Incorrect format. Please use the format: @meddic_bot <gong_call_id>")
        return

    transcript = pull_transcript(match.group(0))
    header,speaker_id_dict = get_transcript_metadate(match.group(0))
    cleaned_transcript = clean_transcript_updated(transcript,speaker_id_dict)
    ai_response = meddic_bot(header + "\n" + cleaned_transcript)
    say(ai_response)


if __name__ == "__main__":
    SocketModeHandler(app, SETTINGS.SLACK_APP_TOKEN).start()
