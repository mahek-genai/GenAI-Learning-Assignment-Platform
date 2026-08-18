import json
import logging
import requests
import streamlit as st
import numpy as np
from PIL import Image
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
import boto3
from scipy.spatial import distance
from components.Parameter_store import S3_BUCKET_NAME

answer = None
show_prompt = None
prompt = None

bedrock_client = boto3.client("bedrock-runtime")
dynamodb = boto3.resource("dynamodb")
assignments_table = dynamodb.Table("assignments")
answers_table = dynamodb.Table("answers")
user_name = "CloudAge-User"

# create a function to retrieve records from DynamoDB table and return a list of records
def get_assignments_from_dynamodb():
    response = assignments_table.scan()
    return response["Items"]

#  create a function to download images from s3 bucket
def download_image(image_name, file_name):
    s3 = boto3.client("s3")
    try:
        s3.download_file(S3_BUCKET_NAME, image_name, file_name)
        return True
    except ClientError as e:
        logging.error(e)
        return False

# function to query a dynamoDB table for a specific key
def get_answer_record_from_dynamodb(student_id, assignment_id, question_id):
    response = answers_table.get_item(
        Key={"student_id": student_id, "assignment_question_id": assignment_id + "_" + str(question_id)}
    )
    return response["Item"]


def get_text_embed(payload):
    input_body = {
        "inputText": payload,
    }
    api_response = bedrock_client.invoke_model(
        body=json.dumps(input_body),
        modelId="amazon.titan-embed-text-v2:0",
        accept="application/json",
        contentType="application/json",
    )
    embedding_response = json.loads(
        api_response.get('body').read().decode('utf-8')
    )
    embedding_array = list(embedding_response['embedding'])
    return embedding_array

# function to query the top five scores for a specific image_id
def get_high_score_answer_records_from_dynamodb(assignment_id, question_id):
    response = answers_table.query(
        IndexName="assignment_question_id-index",
        # query only student_id and score
        ProjectionExpression="student_id, score",
        KeyConditionExpression=Key("assignment_question_id").eq(assignment_id + "_" + str(question_id)),
        # sort by score in descending order
        ScanIndexForward=False,
        Limit=5,
    )
    return response["Items"]


def generate_suggestions_sentence_improvements(text):
    # demonstrate usig Mistral to rephrase the student's answer 
    model_id = 'mistral.mistral-7b-instruct-v0:2'

    input_text = f"""{text}\nImprove the text above in a way that maintains its original meaning but uses different words and sentence structures. Keep your response in 1 sentence."""

    body = json.dumps({
        "prompt": input_text,
        "max_tokens": 400,
        "temperature": 0,
        "top_p": 0.7,
        "top_k": 50
    })

    response = bedrock_client.invoke_model(
        body=body,
        modelId=model_id
    )
    response_body = json.loads(response.get('body').read())
    outputs = response_body.get('outputs')

    output_text = ""
    for index, output in enumerate(outputs):
        output_text = f"{output_text}\n{output['text']}"
        
    return output_text


def generate_suggestions_word_improvements(text):
    #demonstrate using Mistral to correct grammar error
    model_id = 'mistral.mistral-7b-instruct-v0:2'

    input_text = f"""{text}\nReview the text above and correct any grammar errors. Keep your response in 1 sentence."""

    body = json.dumps({
        "prompt": input_text,
        "max_tokens": 400,
        "temperature": 0,
        "top_p": 0.7,
        "top_k": 50
    })

    response = bedrock_client.invoke_model(
        body=body,
        modelId=model_id
    )
    response_body = json.loads(response.get('body').read())
    outputs = response_body.get('outputs')

    output_text = ""
    for index, output in enumerate(outputs):
        output_text = f"{output_text}\n{output['text']}"
        
    return output_text


st.set_page_config(page_title="Answer Questions",  page_icon=":question:", layout="wide")

# Rest of the page
st.markdown("# Answer Questions")
st.sidebar.header("Answer Questions")

# add a list of prompts from DynamoDB
assignment_records = get_assignments_from_dynamodb()
# create a list from the dictionary by prompt
assignment_ids = [record["assignment_id"] for record in assignment_records]
# insert an element at assignment_ids[0]
assignment_ids.insert(0, "<Select>")

assignment_id_selection = st.sidebar.selectbox("Select an assignment", assignment_ids)
assignment_selection = None

if assignment_id_selection and assignment_id_selection != "<Select>":
    # Find the db record with the prompt
    for assignment_record in assignment_records:
        if assignment_record["assignment_id"] == assignment_id_selection:
            assignment_selection = assignment_record

if assignment_selection:
    # Show the image
    image_name = assignment_selection["s3_image_name"]
    file_name = "temp-answer.png"
    if download_image(image_name, file_name):
        st.image(Image.open(file_name), width=128)

    # Show the prompt
    st.write(assignment_selection["prompt"])

    # Select a question
    question_answers_text = assignment_selection["question_answers"]
    question_answers = json.loads(question_answers_text)

    questions = [question_answer["Question"] for question_answer in question_answers]
    generate_question_selection = st.selectbox(
        "Select a question", questions
    )

    answer = st.text_input(
        "Please enter your answer!",
        key="prompt",
    )

    # find answer in the question_answers based on the selected question
    correct_answer = None
    question_id = None
    for question_answer in question_answers:
        if question_answer["Question"] == generate_question_selection:
            correct_answer = question_answer["Answer"]
            question_id = question_answer["Id"]
            break

    if answer and correct_answer:
        st.write("Your guess: ", answer)
        v1 = np.squeeze(np.array(get_text_embed(correct_answer)))
        v2 = np.squeeze(np.array(get_text_embed(answer)))
        dist = distance.cosine(v1, v2)
        score = int(100 - dist * 100)
        # show the result
        st.write(f"Your answer has a score of {score}")

        st.markdown("------------")

        try:
            db_record = get_answer_record_from_dynamodb(
                user_name, assignment_id_selection, question_id
            )
            if db_record["score"] < score:
                db_record["score"] = score
                db_record["answer"] = answer
                answers_table.put_item(Item=db_record)
                st.write(
                    f"Your highest score has been updated. Your new score is {score}"
                    f" and your new answer is '{answer}'."
                )
        except KeyError:
            db_record = {
                "student_id": user_name,
                "assignment_question_id": assignment_id_selection + "_" + str(question_id),
                "answer": answer,
                "score": score,
            }
            answers_table.put_item(Item=db_record)
            st.write(
                f"Your highest score has been updated. Your new score is {score}"
                f" and your new answer is '{answer}'."
            )

        # Query top five scores for the image
        high_score_records = get_high_score_answer_records_from_dynamodb(
            assignment_id_selection, question_id
        )
        # show the high score records
        st.write("Top Three High Scores: ")
        for record in high_score_records:
            st.write(f"Student ID: {record['student_id']} - Score: {record['score']}")

        # Suggested improvements for the answer
        st.markdown("------------")
        st.markdown("Suggested corrections: ")
        st.write(generate_suggestions_word_improvements(answer))

        st.markdown("Suggested sentences: ")
        st.write(generate_suggestions_sentence_improvements(answer))

        if st.button("Show the correct answer"):
            st.write("Answer: ")
            st.write(correct_answer)

        # Show the top three scores for the question
        st.markdown("------------")

hide_streamlit_style = """
    <style>
        #MainMenu {visibility: hidden;}
        footer{ visibility: hidden;}
    </style>
    """

st.markdown(hide_streamlit_style, unsafe_allow_html=True)
